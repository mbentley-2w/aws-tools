#!/usr/bin/env python
#
# TODO:  need to be able to propagate tags to EBS snapshots as well
#
# Example:
#
#     ./propagate-tags.py --profile ProsightMainAdmin --region us-east-1 --propagate-tags AppName,BusinessApp
#     ./propagate-tags.py --profile ProsightMainAdmin --region us-east-1 --propagate-tags AppName,BusinessApp --instance i-0695b7d08f0dbb351
#     ./propagate-tags.py --profile ProsightMainAdmin --region us-east-1 --propagate-tags AppName,BusinessApp --instance i-0695b7d08f0dbb351 --dry-run


import sys
import argparse
import boto3
import botocore.exceptions


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


def set_ebs_tag(volume, key, value):
    """ set tag on EBS volume to key=value """
    print(f"DEBUG: Setting tag '{key}' to '{value}'")
    volume.create_tags(Tags=[{'Key': str(key), 'Value': str(value)}])


parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Propagate EC2 Tags to associated EBS volumes and snapshots")

parser.add_argument('--profile', help='AWS Profile to use from ~/.aws/credentials')
parser.add_argument('--region', help='AWS Region (e.g. us-east-1)')
parser.add_argument('--vpc', help='Limit to specific VPC (e.g. vpc-51400a36)')
parser.add_argument('--instance', help='Limit to specific Instance ID (e.g. i-00248125391db0f4b)')
parser.add_argument('--tag-key', help='Limit to instances with specific tag key set (e.g. "AppName")')
parser.add_argument('--propagate-tags', help='Propagate EC2 tag(s) to EBS volumes and snapshots (comma-separated list, no whitespace)')

parser.add_argument('--dry-run', action='store_true', help='Show what would be done, but dont do it.')
parser.set_defaults(dry_run=False)

args = parser.parse_args()
profile = args.profile
region = args.region
vpc_id = args.vpc
instance_id = args.instance
tag_key = args.tag_key
dry_run = args.dry_run

if args.propagate_tags:
    propagate_tags = args.propagate_tags.split(",")
else:
    propagate_tags = None

if not region:
    region = 'us-east-1'

try:
    # If profile is specified, we use it rather than AWS_PROFILE
    if profile:
        boto3.setup_default_session(profile_name=profile)
    #ec2 = boto3.client('ec2', region_name=region)
    ec2 = boto3.resource('ec2', region_name=region)
except botocore.exceptions.ProfileNotFound as e:
    print(f"ERROR: Profile {profile} not found in your ~/.aws/credentials file")
    raise SystemExit
except:
    print(f"ERROR: Use AWS_PROFILE environemnt variable or --profile to specify a valid profile.")
    raise SystemExit


filters=[]

filters.append({'Name': 'instance-state-name', 'Values': ['running', 'stopped']})

if vpc_id:
    filters.append({'Name': 'vpc-id', 'Values': [vpc_id]})

if instance_id:
    filters.append({'Name': 'instance-id', 'Values': [instance_id]})

if tag_key:
    filters.append({'Name': 'tag-key', 'Values': [tag_key]})

instances = ec2.instances.filter(Filters=filters)

for i in instances:
    name_tag = search_for_tag(i.tags, 'Name')

    instance_tag_value = {}

    if propagate_tags:
        for tag_key in propagate_tags:
            instance_tag_value[tag_key] = search_for_tag(i.tags, tag_key)

    # at this point, the instance_tag_value dict should contain all of the values
    # for each tag that we want to propagate.

    print(f"\n{i.id} {name_tag}")
    print(f"     Tag Values: {instance_tag_value}")

    #for tag_idx, tag in enumerate(i.tags):
    #    tag_key = i.tags[tag_idx]['Key']
    #    tag_val = i.tags[tag_idx]['Value']
    #    print(f"          [{tag_idx}] {tag_key} = {tag_val}")

    print(f"     EBS Volumes:")
    for v in i.volumes.all():
        print(f"          {v.id} ")
        volume_tag_value = {}
        if v.tags:
            # Tags were found on this volume, so lets get the values for each that we want to propagate
            # so that we can do a comparison and print out what we find.
            if propagate_tags:
                for tag_key in propagate_tags:
                    tag_value = search_for_tag(v.tags, tag_key)
                    if tag_value:
                        volume_tag_value[tag_key] = tag_value
                        if instance_tag_value[tag_key] == volume_tag_value[tag_key]:
                            print(f"               Tag '{tag_key}' found and matches instance.")
                        else:
                            print(f"               Tag '{tag_key}' found, but DOES NOT MATCH. <-----------------------")
                            if not dry_run:
                                set_ebs_tag(v, tag_key, instance_tag_value[tag_key])

                    else:
                        print(f"               Tag '{tag_key}' NOT found for volume. <-----------------------")
                        if not dry_run:
                            set_ebs_tag(v, tag_key, instance_tag_value[tag_key])
        else:
            # No tags defined for this volume
            print(f"               No Tags Found. <-----------------------")
            if propagate_tags:
                for tag_key in propagate_tags:
                    if not dry_run:
                        set_ebs_tag(v, tag_key, instance_tag_value[tag_key])

