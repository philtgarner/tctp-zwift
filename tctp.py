import argparse
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom



def get_zone(name:str, abbreviation:str, cts:int, min_percentage:int, max_percentage:int):
    return {
        'name': name,
        'abbreviation': abbreviation,
        'min': cts * min_percentage / 100,
        'max': cts * max_percentage / 100
    }


def get_power_zones(cts_power:int):
    zones = list()
    zones.append(get_zone('Endurance Miles', 'EM', cts_power, 45, 73))
    zones.append(get_zone('Tempo', 'T', cts_power, 80, 85))
    zones.append(get_zone('Steady State', 'SS', cts_power, 86, 90))
    zones.append(get_zone('Climbing Repeat', 'CR', cts_power, 95, 100))
    zones.append(get_zone('Power Interval', 'PI', cts_power, 101, 150))
    return zones

def get_power_percentage(zones, desired_zone, zwift_ftp, midpoint):
    zone_list = list(filter(lambda z: z['abbreviation'] == desired_zone, zones))
    if len(zone_list) == 1:
        zone = zone_list[0]
        desired_power = zone['min'] + ((zone['max'] - zone['min']) * midpoint)
        return desired_power / zwift_ftp
    return 0


def row_has_intervals(csv_row, interval_count):
    if f'Intensity {interval_count}' in csv_row and \
            f'Reps {interval_count}' in csv_row and \
            f'Duration {interval_count}' in csv_row and \
            f'Sets {interval_count}' in csv_row and \
            f'RBI {interval_count}' in csv_row and \
            f'RBS {interval_count}' in csv_row and \
            not csv_row[f'Intensity {interval_count}'].strip() == '' and \
            not csv_row[f'Reps {interval_count}'].strip() == '' and \
            not csv_row[f'Duration {interval_count}'].strip() == '' and \
            not csv_row[f'Sets {interval_count}'].strip() == '' and \
            not csv_row[f'RBI {interval_count}'].strip() == '' and \
            not csv_row[f'RBS {interval_count}'].strip() == '':
        return True
    return False


def get_interval_duration(csv_row, interval_count):
    # Get the durations of each rep
    reps_duration = int(csv_row[f'Reps {interval_count}']) * (int(csv_row[f'Duration {interval_count}']) + int(csv_row[f'RBI {interval_count}']))

    # Get the total duration of all sets
    total_duration = int(csv_row[f'Sets {interval_count}']) * (reps_duration + int(csv_row[f'RBS {interval_count}']))

    # Remove the last RBS (no need to rest after the last set)
    total_duration = total_duration - int(csv_row[f'RBS {interval_count}'])

    # If there is a rest after the sets then add this
    if f'RAS {interval_count}' in csv_row and not csv_row[f'RAS {interval_count}'].strip() == '':
        total_duration = total_duration + int(csv_row[f'RAS {interval_count}'])

    return total_duration


def get_zwift_duration(csv_duration):
    return int(csv_duration * 60)


def generate_workout(csv_row, prefix:str, cts_power, zwift_ftp, midpoint):
    # Get the CTS power zones
    cts_power_zones = get_power_zones(cts_power)

    # Get the title of the workout
    space = '' if len(prefix) == 0 else ' '
    week = csv_row['Week']
    day = csv_row['Day']
    workout_name = f'{prefix}{space}Week {week} {day}'

    # Find the total duration of all intervals in this workout
    # We'll use this to work out how much of the base intensity we need to put between each interval set
    total_intervals_duration = 0
    interval_count = 0
    while row_has_intervals(csv_row, interval_count + 1):
        interval_count = interval_count + 1
        total_intervals_duration = total_intervals_duration + get_interval_duration(csv_row, interval_count)

    # Work out how much of the base intensity we need between each interval set
    warm_up_duration = int(csv_row['Warm up'])
    cool_down_duration = int(csv_row['Cool down'])
    total_duration = int(csv_row['Total duration'])
    filler_duration = get_zwift_duration((total_duration - warm_up_duration - cool_down_duration - total_intervals_duration) / (interval_count + 1))
    base_pace = get_power_percentage(
        zones=cts_power_zones,
        desired_zone=csv_row['Base'],
        zwift_ftp=zwift_ftp,
        midpoint=midpoint
    )

    # Create root element
    workout_file = ET.Element('workout_file')

    # Create the workout metadata
    author = ET.SubElement(workout_file, 'author')
    author.text = 'TCTP Zwift workout generator'
    name = ET.SubElement(workout_file, 'name')
    name.text = workout_name
    description = ET.SubElement(workout_file, 'description')
    sportType = ET.SubElement(workout_file, 'sportType')
    sportType.text = 'bike'

    # Add tag(s)
    tags = ET.SubElement(workout_file, 'tags')
    tctp_tag = ET.SubElement(workout_file, 'tag')
    tctp_tag.set('name', 'TCTP')

    # Add the actual workout
    workout = ET.SubElement(workout_file, 'workout')

    # Add the warm up
    if warm_up_duration > 0:
        warm_up = ET.SubElement(workout, 'Warmup')
        warm_up.set('Duration', str(get_zwift_duration(warm_up_duration)))
        warm_up.set('PowerLow', '0.25')
        warm_up.set('PowerHigh', '0.75')

    # If we need any filler before we get into the intervals add it here
    if filler_duration > 0:
        filler = ET.SubElement(workout, 'SteadyState')
        filler.set('Duration', str(filler_duration))
        filler.set('Power', str(base_pace))

    # Loop through the interval sets and append them to the the XML
    for interval_index in range(1, interval_count + 1):

        # Get the pace for the 'on' part of the intervals
        on_pace = get_power_percentage(
            zones=cts_power_zones,
            desired_zone=csv_row[f'Intensity {interval_index}'],
            zwift_ftp=zwift_ftp,
            midpoint=midpoint
        )

        # Get the pace for the rest sections (default to 0.5)
        off_pace = 0.25

        # Get the number of reps and sets
        reps = int(csv_row[f'Reps {interval_index}'])
        sets = int(csv_row[f'Sets {interval_index}'])

        # Get the duration of all the components of the intervals
        on_duration = get_zwift_duration(int(csv_row[f'Duration {interval_index}']))
        off_duration = get_zwift_duration(int(csv_row[f'RBI {interval_index}']))
        rbs_duration = get_zwift_duration(int(csv_row[f'RBS {interval_index}']))

        # Loop through the sets
        for sets in range(sets):

            # Loop through the reps in the set
            for rep in range(reps):

                # Add the 'on' section
                on = ET.SubElement(workout, 'SteadyState')
                on.set('Duration', str(on_duration))
                on.set('Power', str(on_pace))

                # Add the 'off' section
                off = ET.SubElement(workout, 'SteadyState')
                off.set('Duration', str(off_duration))
                off.set('Power', str(off_pace))

            # If there is a rest between sets (there usually will be if there is more than one set) then add it
            # Only add the RBS if we're not on the last interval
            if rbs_duration > 0 and set != sets - 1:
                rbs = ET.SubElement(workout, 'SteadyState')
                rbs.set('Duration', str(rbs_duration))
                rbs.set('Power', str(off_pace))

        # If the workout consists of multiple sets of intervals then there is usually a rest period between them.
        # Add it if it exists
        if f'RAS {interval_index}' in csv_row and not csv_row[f'RAS {interval_index}'].strip() == '':
            ras_duration = get_zwift_duration(csv_row[f'RAS {interval_index}'])
            if ras_duration > 0:
                rbs = ET.SubElement(workout, 'SteadyState')
                rbs.set('Duration', str(ras_duration))
                rbs.set('Power', str(off_pace))

        # After each interval sets we add any filler to make sure the total duration of the workout is correct
        if filler_duration > 0:
            filler = ET.SubElement(workout, 'SteadyState')
            filler.set('Duration', str(filler_duration))
            filler.set('Power', str(base_pace))

    # Add the cool down
    if cool_down_duration > 0:
        cool_down = ET.SubElement(workout, 'CoolDown')
        cool_down.set('Duration', str(get_zwift_duration(cool_down_duration)))
        cool_down.set('PowerHigh', '0.25')
        cool_down.set('PowerLow', '0.75')

    # Write XML file
    xml_string = minidom.parseString(ET.tostring(workout_file)).toprettyxml(indent="   ")
    with open(f'{workout_name}.zwo', "w") as f:
        f.write(xml_string)

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', help='CSV file containing workout details')
    parser.add_argument('--cts_power', type=int, help='CTS field test power')
    parser.add_argument('--zwift_ftp', type=int, help='FTP as set in Zwift')
    parser.add_argument('--workout_prefix', help='Prefix to give workouts', default='')
    parser.add_argument('--midpoint', type=float, help='The point between the min and max where an interval is set', default=0.5)
    args = parser.parse_args()

    with open(args.csv, 'r') as read_obj:
        csv_reader = csv.DictReader(read_obj)
        for row in csv_reader:
            generate_workout(row, args.workout_prefix, args.cts_power, args.zwift_ftp, args.midpoint)
