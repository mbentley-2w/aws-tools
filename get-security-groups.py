#!/usr/bin/env python

import sys
import argparse
import yaml   # PyYAML
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


def make_tf_safe_sg_name(sg_name):
    safe_name = tf_safe_name(sg_name)
    if not safe_name.endswith('_sg'):
        safe_name += "_sg"
    return safe_name


def tf_safe_name(text):
    """ Remove all unwanted chars from text """
    characters = ' ~`!@#$%^&*()-_=+[]{};:\'\",.<>/?\\|'
    for char in characters:
        if char in text:
            text = text.replace(char, "_")  # replace symbols with an underscore
    return dedup("_", text.lower())         # remove duplicate underscore chars


def dedup(char, text):
    """ Remove adjacent duplicate chars in text """
    for count in range(len(text)):
        if char * 2 in text:
            text = text.replace(char * 2, char)
    return text

def print_rule(rule_type, rule):
    """ Print Ingress or Egress rule """

    # a rule can have a comment that is shown along with the yaml output
    rule_comment = ""

    # The structure of a SG Rule
    #
    # FromPort
    # ToPort
    # IpProtocol
    # IpRanges
    #     [ CidrIp, Description ]
    # Ipv6Ranges
    #     [ CidrIpv6, Description ]
    # UserIdGroupPairs
    #     [ GroupId, UserId, Description ]
    #     [ GroupId, UserId, Description, PeeringStatus, VpcPeeringConnectionId, VpcId ]
    # PrefixListIds
    #
    # TODO: I'm Not sure what PrefixListIds are or what they're used for, so will research
    #       that and add support for it/them later.

    if key_defined_and_not_none('ToPort', rule):
        to_port = rule['ToPort']
    else:
        to_port = "0"

    if key_defined_and_not_none('FromPort', rule):
        from_port = rule['FromPort']
    else:
        from_port = "0"

    source_ip_ranges = []
    if key_defined_and_not_none('IpRanges', rule):
        source_ip_ranges += rule['IpRanges']

    if key_defined_and_not_none('Ipv6Ranges', rule):
        source_ip_ranges += rule['Ipv6Ranges']

    source_sgs = []
    if key_defined_and_not_none('UserIdGroupPairs', rule):
        source_sgs = rule['UserIdGroupPairs']

    #print(f"\nBEGIN -- {rule_type} rule --")
    #for k in list(rule.keys()):
    #    print(f"{k} = {rule[k]}" )
    #print(f"END -- {rule_type} rule --")

    for s in source_sgs:
        #print(f"DEBUG:  {s}")
        if not key_defined_and_not_none('Description', s):
            s['Description'] = ""

        if key_defined_and_not_none('GroupId', s):
            source_sg = s['GroupId']

            if source_sg == sg.id:
                source_sg = "self"
            elif key_defined_and_not_none(source_sg, sg_id_to_name):
                # the sg_id exists in the same VPC so we refer to it by name rather than id
                source_sg = sg_id_to_name[source_sg]
            elif key_defined_and_not_none('PeeringStatus', s):
                peer_account = s['UserId']
                peer_vpc = s['VpcId']
                peering_id = s['VpcPeeringConnectionId']
                rule_comment = source_sg + "-in-" + peer_account + "-" + peer_vpc + "-via-" + peering_id

        print(f"      - {{ type: \"{rule_type}\", proto: \"{rule['IpProtocol']}\", from: \"{from_port}\", to: \"{to_port}\", source: \"{source_sg}\", desc: \"{s['Description']}\" }}", end="")

        if rule_comment:
            print(f" # {rule_comment}")
        else:
            print("")

    for s in source_ip_ranges:
        if not key_defined_and_not_none('Description', s):
            s['Description'] = ""
        source_cidr = ""
        if key_defined_and_not_none('CidrIp', s):
            source_cidr = s['CidrIp']
        if key_defined_and_not_none('CidrIpv6', s):
            source_cidr = s['CidrIpv6']
        print(f"      - {{ type: \"{rule_type}\", proto: \"{rule['IpProtocol']}\", from: \"{from_port}\", to: \"{to_port}\", source: [ \"{source_cidr}\" ], desc: \"{s['Description']}\" }}")


parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Get AWS Security Groups")

parser.add_argument('--profile', help='AWS Profile to use from ~/.aws/credentials')
parser.add_argument('--region', help='AWS Region (e.g. us-east-1)')
parser.add_argument('--vpc', help='AWS VPC (e.g. vpc-51400a36)')
parser.add_argument('--sg', help='Specific SG (e.g. sg-1b409c33)')

args = parser.parse_args()
profile = args.profile
region = args.region
vpc_id = args.vpc
sg_id = args.sg

if not region:
    region = 'us-west-2'

if not vpc_id:
    print("ERROR:  VPC ID is required.")
    raise SystemExit

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


vpc = ec2.Vpc(vpc_id)

if sg_id:
    sgs = vpc.security_groups.filter(GroupIds=[sg_id])
else:
    sgs = vpc.security_groups.all()

sg_id_to_name = {}

for sg in sgs:
    #print(f"sg.id = {sg.id}  sg.group_name = {sg.group_name}")
    sg_id_to_name[sg.id] = sg.group_name

print("security-groups:")
for sg in sgs:
    sg_name_tag = search_for_tag(sg.tags, 'Name')
    if not sg_name_tag:
        sg_name_tag = 'none'
    tf_sg_name = make_tf_safe_sg_name(sg.group_name)
    print(f'  - sg-name: "{sg.group_name}"  # terraform import aws_security_group.{tf_sg_name} {sg.id}')
    print(f'    sg-desc: "{sg.description.strip()}"')
    print(f'    sg-rules:')

    for rule in sg.ip_permissions:
        print_rule('ingress', rule)

    for rule in sg.ip_permissions_egress:
        print_rule('egress', rule)


