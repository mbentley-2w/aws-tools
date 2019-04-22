#!/usr/bin/env python
#
# Import CSV data to a DynamoDB table that uses a simple partition key
#

from __future__ import print_function
import argparse
import boto3
import csv
import logging
from tqdm import tqdm

logger = logging.getLogger()

#
# Main
#

help_description = '''
Import CSV data to a DynamoDB Table.  The 1st column must be unique, as it is used as the partition key.

If --profile is not specified, the AWS_PROFILE environment variable will be used.

If --region is not specified, the AWS_DEFAULT_REGION may be used

See Also:  https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html 

---------------------------------------------------------------------------
Examples:

    ./dynamodb-import.py --table foo --csv bar.csv

---------------------------------------------------------------------------

'''

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description=help_description)

parser.add_argument(
    '--profile',
    help='AWS Profile to use from ~/.aws/credentials or ~/.aws/config')

parser.add_argument(
    '--region',
    help='AWS Region ID (e.g. us-east-1)')

parser.add_argument(
    '--table',
    help='Name of DynamoDB Table to import to')

parser.add_argument(
    '--csv',
    help='CSV file containing data to import.\n'
         'First column name is the partition key.\n'
         'Additional column names should correspond to item fields.\n')

args = parser.parse_args()

profile = args.profile
region = args.region

dynamodb_table = args.table
csv_file = args.csv

if not csv_file:
    print("\nMust specify --csv parameter.  Use --help to show full usage info.\n")
    raise SystemExit

if not dynamodb_table:
    print("\nMust specify --table parameter.  Use --help to show full usage info.\n")
    raise SystemExit

# TODO: Put some exception handling around the boto3 calls
dynamodb = boto3.resource('dynamodb', region_name=region)

table = dynamodb.Table(dynamodb_table)

# Header (the column names in the csv file)
header = []

# Open csv
with open(csv_file, newline='') as csvfile:
    reader = csv.reader(csvfile, delimiter=',')

    # Parse Each Line
    with table.batch_writer() as batch:
        for row_index, row in enumerate(tqdm(reader)):

            if row_index == 0:
                # save the column names to be used as the field names
                header = row
            else:

                if row == "":
                    continue

                # Create JSON Object (build a Dictionary) and push to DynamoDB
                data = {}

                # Iterate over each column
                for field_index, entry in enumerate(header):
                    # we can not add null values to a dynamodb item, so we skip those
                    if row[field_index]:
                        data[entry.lower()] = row[field_index]

                response = batch.put_item(
                   Item=data
                )

