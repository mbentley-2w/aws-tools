#!/usr/bin/env python

import sys
import argparse
import yaml   # PyYAML
import boto3
import botocore.exceptions


parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Gather AWS EC2 KeyPair data")

parser.add_argument('--profile', help='AWS Profile to use from ~/.aws/credentials')

args = parser.parse_args()
profile = args.profile

try:
    # If profile is specified, we use it rather than AWS_PROFILE
    if profile:
        boto3.setup_default_session(profile_name=profile)
    client = boto3.client('iam')
    response = client.list_users()
except botocore.exceptions.ProfileNotFound as e:
    print(f"ERROR: Profile {profile} not found in your ~/.aws/credentials file")
    raise SystemExit
except:
    print(f"ERROR: Use AWS_PROFILE environemnt variable or --profile to specify a valid profile.")
    raise SystemExit

for user in response['Users']:
    username = user['UserName']
    access_keys = client.list_access_keys(UserName=username)
    for key in access_keys['AccessKeyMetadata']:
        if key['Status'] == 'Inactive':
            print(f"Inactive Key: {key}")

