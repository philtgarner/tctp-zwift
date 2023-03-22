import argparse
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import os
import time


FP_CADENCE = 150

def get_zone(name:str, abbreviation:str, cts:int, min_percentage:int, max_percentage:int):
    """
    Produces a TCTP zone with a given name and range
    :param name: The name of the TCTP zone
    :param abbreviation: An abbreviation for the training zone
    :param cts: The CTS test power
    :param min_percentage: The lower end of the power zone as a percentage of the CTS test
    :param max_percentage: The upper end of the power zone as a percentage of the CTS test
    :return: The TCTP zone
    """
    return {
        'name': name,
        'abbreviation': abbreviation,
        'min': cts * min_percentage / 100,
        'max': cts * max_percentage / 100
    }


def get_power_zones(cts_power:int):
    """
    Gets the TCTP power zones as described in the book
    :param cts_power: The CTS test power
    :return: The TCTP power zones
    """
    zones = list()
    zones.append(get_zone('Endurance Miles', 'EM', cts_power, 45, 73))
    zones.append(get_zone('Tempo', 'T', cts_power, 80, 85))
    zones.append(get_zone('Steady State', 'SS', cts_power, 86, 90))
    zones.append(get_zone('Climbing Repeat', 'CR', cts_power, 95, 100))
    zones.append(get_zone('Power Interval', 'PI', cts_power, 101, 150))
    return zones


def get_power_percentage(zones, desired_zone, zwift_ftp, midpoint):
    """
    Gets the power as a percentage of the Zwift FTP.
    This is needed because Zwift workouts are generated using a percentage of FTP rather than raw power
    :param zones: TCTP power zones
    :param desired_zone: The abbreviation of the desired zone
    :param zwift_ftp: FTP according to Zwift
    :param midpoint: The point between the lower and upper bounds of the power zone to use
    :return: The specified power zone as a percentage of Zwift FTP
    """
    zone_list = list(filter(lambda z: z['abbreviation'] == desired_zone, zones))
    if len(zone_list) == 1:
        zone = zone_list[0]
        desired_power = zone['min'] + ((zone['max'] - zone['min']) * midpoint)
        return desired_power / zwift_ftp
    return 0


def row_has_intervals(csv_row, interval_count):
    """
    Checks whether a row has entries for the given interval number
    :param csv_row: A row from the CSV input file
    :param interval_count: The interval to check the presence of
    :return: True if the interval exists, false otherwise
    """
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
    """
    Gets the total duration of one set of intervals including rest between reps, sets and rest after the sets
    :param csv_row: A row from the CSV input file
    :param interval_count: The interval to calculate the duration of
    :return: The total duration of the interval in minutes
    """
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
    """
    Converts from a duration specified in the CSV input file to one for Zwift
    :param csv_duration: The duration in minutes
    :return: The duration for Zwift (in seconds)
    """
    return int(csv_duration) * 60


def get_textual_duration(seconds):
    """
    Gets a textual representation of the time in the format HH:MM:SS or MM:SS if less than one hour
    :param seconds: The duration in seconds
    :return: Textual representation of the duration
    """
    if seconds < 3600:
        return time.strftime('%M:%S', time.gmtime(seconds))
    return time.strftime('%H:%M:%S', time.gmtime(seconds))


def get_workout_period(cts_power_zones, on_zone, zwift_ftp, midpoint, duration_seconds):
    """
    Gets an array of XML elements that represent an interval.
    This is often a single steady state effort but there are exceptions like over-unders and PFPI
    :param cts_power_zones: The CTS power zones
    :param on_zone: The name of the TCTP zone that represents this interval
    :param zwift_ftp: FTP according to Zwift
    :param midpoint: The midpoint in a workout range. For example if the EM zone is from 120-200 Watts and the midpoint is 0.5 then the power used for EM is 160 Watts.
    :param duration_seconds: The duration of this interval in seconds
    :return: An array of XML elements that represent this workout
    """
    # Get the on pace (assuming the effort is a straight up zone)
    on_pace = get_power_percentage(
        zones=cts_power_zones,
        desired_zone=on_zone,
        zwift_ftp=zwift_ftp,
        midpoint=midpoint
    )

    # If we have have found a pace then the interval type maps directly to a zone (e.g. SS)
    if on_pace > 0:
        on = ET.Element('SteadyState')
        on.set('Duration', str(duration_seconds))
        on.set('Power', str(on_pace))
        return [
            {
                'xml': on,
                'description': f"{get_textual_duration(duration_seconds)} @ {int(on_pace*zwift_ftp)} Watts"
            }
        ]

    # If not then the we should check the special cases (e.g. SEPI)
    else:
        # If we haven't found a power zone then try some special cases
        if on_zone == 'SEPI':
            on_pace = get_power_percentage(
                zones=cts_power_zones,
                desired_zone='PI',
                zwift_ftp=zwift_ftp,
                midpoint=0.35
            )
            on = ET.Element('SteadyState')
            on.set('Duration', str(duration_seconds))
            on.set('Power', str(on_pace))
            return [
                {
                    'xml': on,
                    'description': f"{get_textual_duration(duration_seconds)} @ {int(on_pace*zwift_ftp)} Watts"
                }
            ]
        elif on_zone == 'FP':
            on_pace = get_power_percentage(
                zones=cts_power_zones,
                desired_zone='EM',
                zwift_ftp=zwift_ftp,
                midpoint=0.35
            )
            on = ET.Element('SteadyState')
            on.set('Duration', str(duration_seconds))
            on.set('Power', str(on_pace))
            on.set('Cadence', str(FP_CADENCE))
            return [
                {
                    'xml': on,
                    'description': f"{get_textual_duration(duration_seconds)} @ {int(on_pace*zwift_ftp)} Watts @ {FP_CADENCE} RPM"
                }
            ]
        elif on_zone == 'PFPI':
            high_pace = get_power_percentage(
                zones=cts_power_zones,
                desired_zone='PI',
                zwift_ftp=zwift_ftp,
                midpoint=0.8
            )
            low_pace = get_power_percentage(
                zones=cts_power_zones,
                desired_zone='PI',
                zwift_ftp=zwift_ftp,
                midpoint=0.3
            )
            on = ET.Element('Ramp')
            on.set('Duration', str(duration_seconds))
            on.set('PowerLow', str(high_pace))
            on.set('PowerHigh', str(low_pace))
            return [
                {
                    'xml': on,
                    'description': f"{get_textual_duration(duration_seconds)} @ {(high_pace*zwift_ftp)}, fading to {(low_pace*zwift_ftp)} Watts"
                }
            ]
        elif on_zone.lower().strip().startswith('ou'):
            return get_over_under_interval(
                cts_power_zones=cts_power_zones,
                on_zone=on_zone,
                zwift_ftp=zwift_ftp,
                midpoint=midpoint,
                duration_minutes=duration_seconds
            )
        else:
            return None


def get_over_under_interval(cts_power_zones, on_zone, zwift_ftp, midpoint, duration_minutes):
    """
    Gets an array of steady state intervals that represent over-unders
    :param cts_power_zones: The CTS power zones
    :param on_zone: The textual representation of over-unders (e.g. OU (2U,1O))
    :param zwift_ftp: FTP according to Zwift
    :param midpoint: The midpoint in a workout range. For example if the EM zone is from 120-200 Watts and the midpoint is 0.5 then the power used for EM is 160 Watts.
    :param duration_minutes: The duration of the entire over-under session (i.e. not an individual over or under)
    :return: An array of XML elements that represent this over-under
    """
    over_duration = get_zwift_duration(int(re.findall(r"(\d+)o", on_zone.lower())[0]))
    under_duration = get_zwift_duration(int(re.findall(r"(\d+)u", on_zone.lower())[0]))
    over_unders = list()
    over_under_duration = 0

    # Keep adding over and unders until the duration of the intervals is at least as long as we're aiming for
    # According the TCTP the unders are at steady state and the overs are at climbing repeat pace
    while over_under_duration < duration_minutes:
        over_unders.append(get_workout_period(
                cts_power_zones=cts_power_zones,
                on_zone='SS',
                zwift_ftp=zwift_ftp,
                midpoint=midpoint,
                duration_seconds=under_duration
            )[0])
        over_unders.append(get_workout_period(
                cts_power_zones=cts_power_zones,
                on_zone='CR',
                zwift_ftp=zwift_ftp,
                midpoint=midpoint,
                duration_seconds=over_duration
            )[0])

        over_under_duration = over_under_duration + under_duration + over_duration

    return over_unders


def generate_workout(csv_row, prefix:str, cts_power_zones, zwift_ftp, midpoint, directory):
    """
    Generates a ZWO file that represent the training plan described in the CSV row
    :param csv_row: The CSV row representing the workout
    :param prefix: A prefix to add to the week/day workout name
    :param cts_power_zones: The CTS power zones
    :param zwift_ftp: FTP according to Zwift
    :param midpoint: The midpoint in a workout range. For example if the EM zone is from 120-200 Watts and the midpoint is 0.5 then the power used for EM is 160 Watts.
    :param directory: The directory to put the workout files in
    :return: True if the workout was created, false otherwise
    """
    # Get the title of the workout
    space = '' if len(prefix) == 0 else ' '
    week = csv_row['Week']
    day = csv_row['Day']
    workout_name = f'{prefix}{space}Week {week} {day}'
    workout_description = []

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
        workout_description.append(f"{get_textual_duration(get_zwift_duration(warm_up_duration))} warm-up")

    # If we need any filler before we get into the intervals add it here
    if filler_duration > 0:
        filler = ET.SubElement(workout, 'SteadyState')
        filler.set('Duration', str(filler_duration))
        filler.set('Power', str(base_pace))
        workout_description.append(f"{get_textual_duration(filler_duration)} @ {int(base_pace*zwift_ftp)} Watts")

    # Loop through the interval sets and append them to the the XML
    for interval_index in range(1, interval_count + 1):

        # Get the pace for the 'on' part of the intervals
        on_zone = csv_row[f'Intensity {interval_index}'].strip().upper()
        on_pace = get_power_percentage(
            zones=cts_power_zones,
            desired_zone=on_zone,
            zwift_ftp=zwift_ftp,
            midpoint=midpoint
        )

        # Get the pace for the rest sections (default to 0.5)
        off_pace = 0.5

        # Get the number of reps and sets
        reps = int(csv_row[f'Reps {interval_index}'])
        sets = int(csv_row[f'Sets {interval_index}'])

        # Get the duration of all the components of the intervals
        on_duration = get_zwift_duration(int(csv_row[f'Duration {interval_index}']))
        off_duration = get_zwift_duration(int(csv_row[f'RBI {interval_index}']))
        rbs_duration = get_zwift_duration(int(csv_row[f'RBS {interval_index}']))

        # Loop through the sets
        for set in range(sets):

            # Loop through the reps in the set
            for rep in range(reps):

                # Add the 'on' section(s)
                on = get_workout_period(
                    cts_power_zones=cts_power_zones,
                    on_zone=on_zone,
                    zwift_ftp=zwift_ftp,
                    midpoint=midpoint,
                    duration_seconds=on_duration
                )

                # In some cases (e.g. over-unders) there will be more than one component to the interval
                # Add them all
                for o in on:
                    workout.append(o['xml'])
                    workout_description.append(o['description'])

                # Add the 'off' section
                off = ET.SubElement(workout, 'SteadyState')
                off.set('Duration', str(off_duration))
                off.set('Power', str(off_pace))
                workout_description.append(f"{get_textual_duration(off_duration)} @ {int(off_pace*zwift_ftp)} Watts")


            # If there is a rest between sets (there usually will be if there is more than one set) then add it
            # Only add the RBS if we're not on the last interval
            if rbs_duration > 0 and set != sets - 1:
                rbs = ET.SubElement(workout, 'SteadyState')
                rbs.set('Duration', str(rbs_duration))
                rbs.set('Power', str(off_pace))
                workout_description.append(f"{get_textual_duration(rbs_duration)} @ {int(off_pace*zwift_ftp)} Watts")

        # If the workout consists of multiple sets of intervals then there is usually a rest period between them.
        # Add it if it exists
        if f'RAS {interval_index}' in csv_row and not csv_row[f'RAS {interval_index}'].strip() == '':
            ras_duration = get_zwift_duration(csv_row[f'RAS {interval_index}'])
            if ras_duration > 0:
                rbs = ET.SubElement(workout, 'SteadyState')
                rbs.set('Duration', str(ras_duration))
                rbs.set('Power', str(off_pace))
                workout_description.append(f"{get_textual_duration(ras_duration)} @ {int(off_pace*zwift_ftp)} Watts")

        # After each interval sets we add any filler to make sure the total duration of the workout is correct
        if filler_duration > 0:
            filler = ET.SubElement(workout, 'SteadyState')
            filler.set('Duration', str(filler_duration))
            filler.set('Power', str(base_pace))
            workout_description.append(f"{get_textual_duration(filler_duration)} @ {int(base_pace*zwift_ftp)} Watts")

    # Add the cool down
    if cool_down_duration > 0:
        cool_down = ET.SubElement(workout, 'CoolDown')
        cool_down.set('Duration', str(get_zwift_duration(cool_down_duration)))
        cool_down.set('PowerHigh', '0.25')
        cool_down.set('PowerLow', '0.75')
        workout_description.append(f"{get_textual_duration(get_zwift_duration(cool_down_duration))} cool-down")

    # If the directory for the output files doesn't exist then make it.
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Write XML file
    xml_string = minidom.parseString(ET.tostring(workout_file)).toprettyxml(indent="   ")
    with open(f'{directory}/{workout_name}.zwo', "w") as f:
        f.write(xml_string)

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', help='CSV file containing workout details')
    parser.add_argument('--cts_power', type=int, help='CTS field test power')
    parser.add_argument('--zwift_ftp', type=int, help='FTP as set in Zwift')
    parser.add_argument('--workout_prefix', help='Prefix to give workouts', default='')
    parser.add_argument('--midpoint', type=float, help='The point between the min and max where an interval is set', default=0.5)
    parser.add_argument('--directory', help='The directory to put the output files in', default='output')
    args = parser.parse_args()

    with open(args.csv, 'r') as read_obj:
        csv_reader = csv.DictReader(read_obj)

        # Get the CTS power zones
        cts_power_zones = get_power_zones(args.cts_power)

        # Loop over each row in the CSV and create a workout for each row
        for row in csv_reader:
            generate_workout(
                csv_row=row,
                prefix=args.workout_prefix,
                cts_power_zones=cts_power_zones,
                zwift_ftp=args.zwift_ftp,
                midpoint=args.midpoint,
                directory=args.directory
            )
