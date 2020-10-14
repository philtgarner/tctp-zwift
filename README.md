# TCTP to Zwift

The _Time Crunched Cyclist_ by Chris Carmichael and Jim Rutberg contains a number of training plans and Zwift is one of the most popular indoor training platforms.
This Python script transforms TCTP training plans into Zwift workouts so you don't have to manually create each one.

## TCTP training plan format

The script requires a CSV file containing the training plan in the following format (all durations are specified in minutes):

| Week | Day      | Total duration | Warm up | Cool down | Base | Intensity 1 | Reps 1 | Duration 1 | Sets 1 | RBI 1 | RBS 1 | RAS 1 | Intensity 2 | Reps 2 | Duration 2 | Sets 2 | RBI 2 | RBS 2 | RAS 2 |
|------|----------|----------------|---------|-----------|------|-------------|--------|------------|--------|-------|-------|-------|-------------|--------|------------|--------|-------|-------|-------|
| 8    | Thursday | 60             | 5       | 5         | EM   | PFPI        | 4      | 2          | 1      | 2     | 0     | 8     | OU (2U,1O)  | 4      | 3          | 1      | 3     | 0     |       |

The above example is the CSV representation of:

> 60 min. EM with 4 x 2 min PFPI (2 min RBI); rest 8 min; 4 x 3 min OU (2U, 1O) (3 min RBI)

The following columns are mandatory for every workout:

- Week
- Day
- Total duration
- Warm up
- Cool down
- Base

A workout can consist of any number of interval blocks and each interval block should consist of the following columns (where _n_ is the index of the interval block in the workout, starting at 1):

- Intensity n
- Reps n
- Duration n
- Sets n
- RBI n
- RBS n
- RAS n

All of the above terms are explained in the TCTP book with the exception of RAS which refers to _Rest After Sets_ and is the rest period before the next set of intervals begins.

## Supported interval terms

- EM
- T
- SS
- CR
- PI
- SEPI
- OU (2U, 1O)
- FP
- PFPI
