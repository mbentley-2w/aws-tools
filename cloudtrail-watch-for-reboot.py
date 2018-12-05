# Inspired by re:Invent 2017 workshop:
#
#     SID 341: Using AWS CloudTrail Logs for Scalable, Automated Anomaly Detection
#     https://github.com/aws-samples/aws-cloudtrail-analyzer-workshop
#
# Requires IAM Permissions:
#
# {
#     "Version": "2012-10-17",
#     "Statement": [
#         {
#             "Effect": "Allow",
#             "Action": "ec2:Describe*",
#             "Resource": "*"
#         },
#         {
#             "Effect": "Allow",
#             "Action": [
#                 "logs:*"
#             ],
#             "Resource": "arn:aws:logs:*:*:*"
#         },
#         {
#             "Effect": "Allow",
#             "Action": [
#                 "s3:GetObject"
#             ],
#             "Resource": [
#                 "<CloudTrail log bucket ARN>/*"
#             ]
#         },
#         {
#             "Effect": "Allow",
#             "Action": [
#                 "sns:Publish"
#             ],
#             "Resource": [
#                 "<SNS Topic ARN>"
#             ]
#         }
#     ]
# }


import io
import gzip
import json
import boto3
import logging
import botocore
import botocore.exceptions

logger = logging.getLogger()

# Hack to work when executed under AWS Lambda
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)

logging.basicConfig(
    format='%(levelname)s:%(name)s:%(message)s',
    level=logging.INFO)


def get_records(session, bucket, key):
    """
    Loads a CloudTrail log file, decompresses it, and extracts its records.

    :param session: Boto3 session
    :param bucket: Bucket where log file is located
    :param key: Key to the log file object in the bucket
    :return: list of CloudTrail records
    """

    try:
        s3 = session.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
    except botocore.exceptions.ClientError as e:
        logger.error(e)
        raise SystemExit
    except botocore.exceptions.NoCredentialsError as e:
        logger.error(e)
        raise SystemExit

    with io.BytesIO(response['Body'].read()) as obj:
        with gzip.GzipFile(fileobj=obj) as logfile:
            records = json.load(logfile)['Records']
            sorted_records = sorted(records, key=lambda r: r['eventTime'])
            return sorted_records


def get_log_file_location(event):
    """
    Generator for the bucket and key names of each CloudTrail log
    file contained in the event sent to this function from S3.
    (usually only one but this ensures we process them all).

    :param event: S3:ObjectCreated:Put notification event
    :return: yields bucket and key names
    """
    for event_record in event['Records']:
        bucket = event_record['s3']['bucket']['name']
        key = event_record['s3']['object']['key']
        yield bucket, key


def parse_arn(arn):
    """
    Given an ARN in proper format, will return a dictionary with the various
    components accessible by name.
    :param arn: AWS-compliant Resource Identifier
    :return: dictionary of ARN components
    """
    # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
    elements = arn.split(':', 5)
    result = {
        'arn': elements[0],
        'partition': elements[1],
        'service': elements[2],
        'region': elements[3],
        'account': elements[4],
        'resource': elements[5],
        'resource_type': None
    }
    if '/' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split('/', 1)
    elif ':' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split(':', 1)
    return result


def search_for_tag(list_of_dicts, search_tag):
    """
    Given the instance tags and one to search for, will return the value of search_tag if found
    Otherwise, if empty or non-existent, will return None
    :param list_of_dicts: instance tags
    :param search_tag: tag key to search for
    :return: value of search_tag or None
    """
    if not list_of_dicts:
        return None
    found_tag = next((item for item in list_of_dicts if item["Key"] == search_tag), None)
    if found_tag:
        return found_tag['Value']
    else:
        return None


def get_ec2_tag(session, instance_id, tag_key):
    """
    Search for an instance's tag, and return the value if exists
    :param session:  the boto3 session object
    :param instance_id:  the EC2 instance ID
    :param tag_key:  the tag we are searching for
    :return:  the value associated with tag_key
    """
    ec2 = session.resource('ec2', region_name='us-west-2')

    filters = [
        {'Name': 'instance-id', 'Values': [instance_id]},
        {'Name': 'tag-key', 'Values': [tag_key]}
    ]

    try:
        instances = ec2.instances.filter(Filters=filters)
    except botocore.exceptions.ClientError as e:
        logger.error(e)
        raise SystemExit
    except botocore.exceptions.NoCredentialsError as e:
        logger.error(e)
        raise SystemExit

    if instances and len(list(instances)) == 1:
        # There should only ever be one as we filter on instance ID
        instance = list(instances)[0]
        return search_for_tag(instance.tags, tag_key)
    else:
        return None


def main(event=None):

    # used in the SNS message
    event_json = json.dumps(event, indent=4)

    # Create a Boto3 session that can be used to construct clients
    session = boto3.session.Session()

    # Get the S3 bucket and key for each log file contained in the event
    for bucket, key in get_log_file_location(event):
        # Load the CloudTrail log file and extract its records
        logger.info(f'Loading CloudTrail log file s3://{bucket}/{key}')
        records = get_records(session, bucket, key)
        logger.info(f'Number of records in log file: {len(records)}')

        # Process the CloudTrail records
        for record_number, record in enumerate(records):

            # save the CloutTrail event as json to be used in the SNS message
            record_json = json.dumps(record, indent=4)

            if 'eventName' in record.keys():

                # TODO: We are only looking for RebootInstances events at this time, but should generalize this
                # TODO: to be more useful for watching for any type of event
                if record['eventName'] == 'RebootInstances':
                    param_items = record['requestParameters']['instancesSet']['items']
                    for item_number, item in enumerate(param_items):
                        instance_id = item['instanceId']
                        logger.info(f"Record {record_number}:{item_number} --> Instance {instance_id} was rebooted")

                        sns_topic_arn = get_ec2_tag(session, instance_id, 'alert_topic_arn')

                        if sns_topic_arn:
                            logger.info(f"Alerting to SNS Topic: {sns_topic_arn}")
                            # extract the region from the arn and setup sns client
                            arn_components = parse_arn(sns_topic_arn)
                            sns_region = arn_components['region']
                            name_tag = get_ec2_tag(session, instance_id, 'Name')
                            sns_message = f"*** EC2 Instance Rebooted ***\n\nInstance ID: {instance_id}\n"
                            sns_message += f"Name Tag: {name_tag}\n\n"
                            sns_message += f"*** CloudTrail Event ***\n\n{record_json}\n\n"
                            sns_message += f"*** Lambda Triggering Event ***\n\n{event_json}\n\n"
                            sns = session.client('sns', region_name=sns_region)
                            sns.publish(TopicArn=sns_topic_arn, Message=sns_message)
                        else:
                            logger.info(f"Tag 'alert_topic_arn' not found on instance {instance_id}")


def lambda_handler(event, context):
    main(event=event)


if __name__ == '__main__':

    test_event = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-west-2",
                "eventTime": "2018-12-04T19:33:23.243Z",
                "eventName": "ObjectCreated:Put",
                "userIdentity": {
                    "principalId": "AWS:ARXAX5XDX4XU2GUZPLP4Y:i-014dc58ff5920b303"
                },
                "requestParameters": {
                    "sourceIPAddress": "34.222.16.186"
                },
                "responseElements": {
                   "x-amz-request-id": "66A59FDD49DEC281",
                   "x-amz-id-2": "60T/uZu8u0Pcya8A4u5N62u9YiUSMuluxYb5uIQec33v8uBGqEufkPZpuPdUuzautXW/R1PCeRg="
                },
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "e16d29d3-9160-47c3-b453-0dd0d11511f6",
                    "bucket": {
                        "name": "mbentley-cloud-trail",
                        "ownerIdentity": {
                            "principalId": "AKVMYSGWVJEZA"
                        },
                        "arn": "arn:aws:s3:::mbentley-cloud-trail"
                    },
                    "object": {
                        "key": "AWSLogs/305170822333/CloudTrail/us-west-2/2018/12/04/305170822333_CloudTrail_us-west-2_20181204T1930Z_CVF8AF5kHYG8UDxK.json.gz",
                        "size": 4575,
                        "eTag": "cd0b2a2677988b1e90a5e58f776b26af",
                        "sequencer": "005C06D6832B283BF5"
                    }
                }
            }
        ]
    }

    main(event=test_event)

