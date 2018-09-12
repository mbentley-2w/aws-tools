#!/usr/bin/env python

import sys
import argparse
import boto3
import botocore.exceptions

#
# Helper Functions
#

def key_defined_and_not_none(this_key, this_dict):
    """ Check if key is defined within dictionary, and not None (null) """
    if this_dict and (this_key in this_dict) and this_dict[this_key]:
        return True
    else:
        return False


def search_for_tag(list_of_dicts, search_tag):
    """ Given the tags for an AWS resource, returns it if it finds it. """
    if not list_of_dicts:
        return None
    found_tag = next((item for item in list_of_dicts if item["Key"] == search_tag), False)
    if found_tag:
        return found_tag['Value']
    else:
        return None


def set_tag(resource, key, value):
    """ set EBS volume or snapshot tag key to value """
    # print(f"DEBUG: Setting tag '{key}' to '{value}'")
    resource.create_tags(Tags=[{'Key': str(key), 'Value': str(value)}])


def tag_match(instance, resource, tag_key):
    """ given volume or snapshot resource, check if the instance tag value matches that resource's tag value """

    instance_tag_value = search_for_tag(instance.tags, tag_key)
    resource_tag_value = search_for_tag(resource.tags, tag_key)

    if instance_tag_value == resource_tag_value:
        return True
    else:
        return False


def print_volume_tag_status(instance, volume, tag_key):
    if search_for_tag(instance.tags, tag_key):
        if tag_match(instance, volume, tag_key):
            tag_status = 'Match'
        else:
            tag_status = 'Differs'
    else:
        # Given tag_key not defined for the instance
        tag_status = 'Missing on Instance'
    print(f"{instance.id}  {volume.id}                          {tag_status}")


def print_snapshot_tag_status(instance, volume, snapshot, tag_key):
    if search_for_tag(instance.tags, tag_key):
        if tag_match(instance, snapshot, tag_key):
            tag_status = 'Match'
        else:
            tag_status = 'Differs'
    else:
        # Given tag_key not defined for the instance
        tag_status = 'Missing on Instance'
    print(f"{instance.id}  {volume.id}  {snapshot.id}  {tag_status}")


def print_report(instances, tag_key):
    print(f"-------------------  ---------------------  ----------------------  -------------------")
    print(f"Instance             Volume                 Snapshot                Tag Status")
    print(f"-------------------  ---------------------  ----------------------  -------------------")
    for i in instances:
        volumes = i.volumes.all()
        for v in volumes:
            print_volume_tag_status(i, v, tag_key)
            snapshots = v.snapshots.all()
            for ss in snapshots:
                print_snapshot_tag_status(i, v, ss, tag_key)
        print(f"-------------------  ---------------------  ----------------------  -------------------")


def propagate_tag_to_volume(instance, volume, tag_key, dry_run):
    if tag_match(instance, volume, tag_key):
        tag_status = 'Already Matches'
    else:
        old_tag_value = search_for_tag(volume.tags, tag_key) or 'None'
        new_tag_value = search_for_tag(instance.tags, tag_key)
        if dry_run:
            tag_status = f"Differs - Would Update ({old_tag_value} --> {new_tag_value})"
        else:
            tag_status = f"Differs - Updating ({old_tag_value} --> {new_tag_value})"
            set_tag(volume, tag_key, new_tag_value)
    print(f"{instance.id}  {volume.id}                          {tag_status}")


def propagate_tag_to_snapshot(instance, volume, snapshot, tag_key, dry_run):
    if tag_match(instance, snapshot, tag_key):
        tag_status = 'Already Matches'
    else:
        old_tag_value = search_for_tag(snapshot.tags, tag_key) or 'None'
        new_tag_value = search_for_tag(instance.tags, tag_key)
        if dry_run:
            tag_status = f"Differs - Would Update ({old_tag_value} --> {new_tag_value})"
        else:
            tag_status = f"Differs - Updating ({old_tag_value} --> {new_tag_value})"
            set_tag(snapshot, tag_key, new_tag_value)
    print(f"{instance.id}  {volume.id}  {snapshot.id}  {tag_status}")


def propagate_tag(instances, tag_key, dry_run):
    print(f"-------------------  ---------------------  ----------------------  -------------------")
    print(f"Instance             Volume                 Snapshot                Tag Status")
    print(f"-------------------  ---------------------  ----------------------  -------------------")
    for instance in instances:
        # If the tag_key is defined on the instance, we propagate it to all volumes and snapshots
        if search_for_tag(instance.tags, tag_key):
            volumes = instance.volumes.all()
            for volume in volumes:
                propagate_tag_to_volume(instance, volume, tag_key, dry_run)
                snapshots = volume.snapshots.all()
                for snapshot in snapshots:
                    propagate_tag_to_snapshot(instance, volume, snapshot, tag_key, dry_run)
        else:
            print(f"{instance.id}  --> Tag key '{tag_key}' not defined or has no value.  Skipping.")
        print(f"-------------------  ---------------------  ----------------------  -------------------")


#
# Main
#

help_description = '''
Propagate a single EC2 Instance Tag to associated EBS Volumes and Snapshots

If --profile is not specified, the AWS_PROFILE environment variable will be used.

If --region is not specified, it will default to "us-east-1"

---------------------------------------------------------------------------
Examples:
    
    Report on the status of tag with key "AppName"

        ./propagate-tags.py --report --tag AppName:

    Report on the status of tag with key "AppName" limited to a specific VPC

        ./propagate-tags.py --report --tag AppName --vpc vpc-3d4b2c5ap

    Report on the status of tag with key "AppName" limited to a Instance ID:

        ./propagate-tags.py --report --tag AppName --instance i-0695b7d08f0dbb351

    Propagate the instance tag key and value to all associated volumes and snapshots:

        ./propagate-tags.py --propagate --tag AppName
        
    A "Dry Run" will show what would be done, but not actually do it:

        ./propagate-tags.py --propagate --tag AppName --dry-run
        
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
    '--vpc',
    help='Limit to specific VPC ID (e.g. vpc-51400a36)')

parser.add_argument(
    '--instance',
    help='Limit to specific Instance ID (e.g. i-00248125391db0f4b)')

parser.add_argument(
    '--tag-key',
    help='Limit to instances with specific tag key defined, regardless of its value (e.g. "AppName")')

parser.add_argument(
    '--tag',
    help='The tag to report on or propagate (required with --report or --propagate)')

parser.add_argument(
    '--report',
    action='store_true',
    help='Print a report of the current state of given tag (--tag required)')

parser.add_argument(
    '--propagate',
    action='store_true',
    help='Propagate given EC2 tag to EBS volumes and snapshots (--tag required)')

parser.add_argument(
    '--dry-run',
    action='store_true',
    help='Show what would be done, but dont do it.')

parser.set_defaults(report=False)
parser.set_defaults(propagate=False)
parser.set_defaults(dry_run=False)

if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    raise SystemExit

args = parser.parse_args()

profile = args.profile
region = args.region

limit_vpc_id = args.vpc
limit_instance_id = args.instance
limit_tag_key = args.tag_key

dry_run = args.dry_run
report = args.report
propagate = args.propagate
tag_key = args.tag

if report and propagate:
    print(f"\nCannot specify both --report and --propagate at the same time!  Use --help to show full usage info.\n")
    raise SystemExit

if not (report or propagate):
    print(f"\nMust specify either --report or --propagate options!  Use --help to show full usage info.\n")
    raise SystemExit

if not tag_key:
    print(f"\nMust specify --tag <tag key> to report on or propagate!  Use --help to show full usage info.\n")
    raise SystemExit

if not region:
    region = 'us-east-1'

try:
    # If profile is specified, we use it rather than AWS_PROFILE
    if profile:
        boto3.setup_default_session(profile_name=profile)
    ec2 = boto3.resource('ec2', region_name=region)
except botocore.exceptions.ProfileNotFound as e:
    print(f"ERROR: Profile {profile} not found in your ~/.aws/credentials file")
    raise SystemExit
except:
    print(f"ERROR: Use AWS_PROFILE environemnt variable or --profile to specify a valid profile.")
    raise SystemExit


filters = []

filters.append({'Name': 'instance-state-name', 'Values': ['running', 'stopped']})

if limit_vpc_id:
    filters.append({'Name': 'vpc-id', 'Values': [limit_vpc_id]})

if limit_instance_id:
    filters.append({'Name': 'instance-id', 'Values': [limit_instance_id]})

if limit_tag_key:
    filters.append({'Name': 'tag-key', 'Values': [limit_tag_key]})

instances = []

try:
    instances = ec2.instances.filter(Filters=filters)

    if report:
        print_report(instances, tag_key)

    elif propagate:
        propagate_tag(instances, tag_key, dry_run)

except KeyboardInterrupt:
    print(f"\nHow wewd!")
    raise SystemExit

except botocore.exceptions.ClientError as e:
    print(f"\nERROR: {e}")
    raise SystemExit

