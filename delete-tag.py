#!/usr/bin/env python

import sys
import argparse
import boto3
import botocore.exceptions

#
# Helper Functions
#

def search_for_tag(list_of_dicts, search_tag):
    """ Given the tags for an AWS resource, returns it if it finds it. """
    if not list_of_dicts:
        return None
    found_tag = next((item for item in list_of_dicts if item["Key"] == search_tag), False)
    if found_tag:
        return found_tag['Value']
    else:
        return None


#
# Main
#

help_description = '''
Delete a single tag on EC2 Instance and associated EBS Volumes and Snapshots

If --profile is not specified, the AWS_PROFILE environment variable will be used.

If --region is not specified, it will default to "us-east-1"

---------------------------------------------------------------------------
Examples:

    Report on the status of tag with key "AppName"

        ./delete-tag.py --report --tag AppName

    Report on the status of tag with key "AppName" limited to a Instance ID:

        ./delete-tag.py --report --tag AppName --instance i-0695b7d08f0dbb351

    Delete the specified tag across EC2 Instance, and associated Volumes and Snapshots

        ./delete-tag.py --delete --tag AppName

    A "Dry Run" will show what would be done, but not actually do it:

        ./delete-tag.py --delete --tag AppName --dry-run

---------------------------------------------------------------------------

'''

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description=help_description)

parser.add_argument(
    '--profile',
    help='AWS Profile to use from ~/.aws/credentials')

parser.add_argument(
    '--region',
    help='AWS Region ID (e.g. us-east-1)')

parser.add_argument(
    '--instance',
    help='Limit to specific Instance ID (e.g. i-00248125391db0f4b)')

parser.add_argument(
    '--tag',
    help='The tag to report on or delete (required with --report or --delete)')

parser.add_argument(
    '--report',
    action='store_true',
    help='Print a report of the current state of given tag (--tag required)')

parser.add_argument(
    '--delete',
    action='store_true',
    help='Delete given tag from EC2 instance, EBS volumes and snapshots (--tag required)')

parser.add_argument(
    '--dry-run',
    action='store_true',
    help='Show what would be done, but dont do it.')

parser.set_defaults(report=False)
parser.set_defaults(delete=False)
parser.set_defaults(dry_run=False)

if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    raise SystemExit

args = parser.parse_args()

profile = args.profile
region = args.region

limit_instance_id = args.instance

dry_run = args.dry_run
report = args.report
delete = args.delete
tag_key = args.tag

if report and delete:
    print(f"\nCannot specify both --report and --delete at the same time!  Use --help to show full usage info.\n")
    raise SystemExit

if not (report or delete):
    print(f"\nMust specify either --report or --delete options!  Use --help to show full usage info.\n")
    raise SystemExit

if not tag_key:
    print(f"\nMust specify --tag <tag key> to report on or delete!  Use --help to show full usage info.\n")
    raise SystemExit

if not region:
    region = 'us-east-1'

try:
    # If profile is specified, we use it rather than AWS_PROFILE
    if profile:
        boto3.setup_default_session(profile_name=profile)
    ec2_client = boto3.client('ec2', region_name=region)
except botocore.exceptions.ProfileNotFound as e:
    print(f"ERROR: Profile {profile} not found in your ~/.aws/credentials file")
    raise SystemExit
except:
    print(f"ERROR: Use AWS_PROFILE environemnt variable or --profile to specify a valid profile.")
    raise SystemExit


instance_filters = []
volume_filters = []
snapshot_filters = []

instance_filters.append({'Name': 'instance-state-name', 'Values': ['running', 'stopped']})

if limit_instance_id:
    instance_filters.append({'Name': 'instance-id', 'Values': [limit_instance_id]})
    volume_filters.append({'Name': 'attachment.instance-id', 'Values': [limit_instance_id]})

instance_filters.append({'Name': 'tag-key', 'Values': [tag_key]})
volume_filters.append({'Name': 'tag-key', 'Values': [tag_key]})
snapshot_filters.append({'Name': 'tag-key', 'Values': [tag_key]})


try:
    response = ec2_client.describe_instances(Filters=instance_filters)
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            print(f"{instance_id}: ", end='')
            print("{} = {}".format(tag_key, search_for_tag(instance['Tags'], tag_key)), end='')
            if delete and not dry_run:
                ec2_delete_tags_response = ec2_client.delete_tags(
                    Resources=[
                        instance_id,
                    ],
                    Tags=[
                        {
                            'Key': tag_key
                        },
                    ]
                )
                print(f" (Deleted tag '{tag_key}')")
            else:
                print("")

    volume_response = ec2_client.describe_volumes(Filters=volume_filters)
    for volume in volume_response['Volumes']:
        volume_id = volume['VolumeId']
        print(f"{volume_id}: ", end='')
        print("{} = {}".format(tag_key, search_for_tag(volume['Tags'], tag_key)), end='')
        if delete and not dry_run:
            volume_delete_tags_response = ec2_client.delete_tags(
                Resources=[
                    volume_id,
                ],
                Tags=[
                    {
                        'Key': tag_key
                    },
                ]
            )
            print(f" (Deleted tag '{tag_key}')")
        else:
            print("")

    snapshot_response = ec2_client.describe_snapshots(Filters=snapshot_filters, OwnerIds=['self'])
    for snapshot in snapshot_response['Snapshots']:
        snapshot_id = snapshot['SnapshotId']
        print(f"{snapshot_id}: ", end='')
        print("{} = {}".format(tag_key, search_for_tag(snapshot['Tags'], tag_key)), end='')
        if delete and not dry_run:
            snapshot_delete_tags_response = ec2_client.delete_tags(
                Resources=[
                    snapshot_id,
                ],
                Tags=[
                    {
                        'Key': tag_key
                    },
                ]
            )
            print(f" (Deleted tag '{tag_key}')")
        else:
            print("")

except KeyboardInterrupt:
    print(f"\nHow wewd!")
    raise SystemExit

except botocore.exceptions.ClientError as e:
    print(f"\nERROR: {e}")
    raise SystemExit

