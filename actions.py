import boto3
import logging
from botocore.config import Config
from os import getenv
from datetime import datetime

logger = logging.getLogger()
log_level = getenv("LOGLEVEL", "INFO")
level = logging.getLevelName(log_level)
logger.setLevel(level)


def boto3_client(resource, assumed_credentials=None):
    config = Config(
        retries=dict(
            max_attempts=40
        )
    )
    if assumed_credentials:
        client = boto3.client(
            resource,
            aws_access_key_id=assumed_credentials['AccessKeyId'],
            aws_secret_access_key=assumed_credentials['SecretAccessKey'],
            aws_session_token=assumed_credentials['SessionToken'],
            config=config
        )
    else:
        client = boto3.client(
            resource,
            config=config
        )

    return client


def check_alarm_tag(instance_id, tag_key):
    try:
        ec2_client = boto3_client('ec2')
        # does instance have appropriate alarm tag?
        instance = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'tag-key',
                    'Values': [
                        tag_key
                    ]
                }
            ],
            InstanceIds=[
                instance_id
            ]

        )
        # can only be one instance when called by CloudWatch Events
        if 'Reservations' in instance and len(instance['Reservations']) > 0 and len(
                instance['Reservations'][0]['Instances']) > 0:
            ec2_client.create_tags(
                Resources=[
                    instance_id
                ],
                Tags=[
                    {
                        'Key': tag_key,
                        'Value': str(datetime.utcnow())
                    }
                ]
            )
            return instance['Reservations'][0]['Instances'][0]
        else:
            return False

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Failure describing instance {} with tag key: {} : {}'.format(instance_id, tag_key, e))
        raise


def process_alarm_tags(instance_id, instance_info, default_alarms, metric_dimensions_map, sns_topic_arn, append_dimensions, cw_namespace):
    instance_tags = instance_info['Tags']
    ImageId = instance_info['ImageId']
    logger.info('ImageId is: {}'.format(ImageId))
    platform = determine_platform(ImageId)

    logger.info('Platform is: {}'.format(platform))
    # get all alarm tags from instance and add them into the tag list
    for instance_tag in instance_tags:
        if instance_tag['Key'].startswith('AutoAlarm'):
            custom_alarm_properties = instance_tag['Key'].split('-')
            custom_alarm_namespace = custom_alarm_properties[1]
            if custom_alarm_namespace == 'AWS/EC2':
                default_alarms['All'].append(instance_tag)
            elif custom_alarm_namespace == cw_namespace:
                default_alarms[platform].append(instance_tag)

    # process standard AWS/EC2 alarms across all platforms - dimensions are static here.
    for tag in default_alarms['All']:
        alarm_properties = tag['Key'].split('-')
        Namespace = alarm_properties[1]
        MetricName = alarm_properties[2]
        ComparisonOperator = alarm_properties[3]
        Period = alarm_properties[4]
        Statistic = alarm_properties[5]

        # AWS/EC2 namespace dimensions only include InstanceId
        Dimensions = [
            {
                'Name': 'InstanceId',
                'Value': instance_id
            }
        ]

        AlarmName = 'AutoAlarm-{}-{}-{}-{}-{}'.format(instance_id, MetricName, ComparisonOperator, tag['Value'],
                                                      Period)
        create_alarm(AlarmName, MetricName, ComparisonOperator, Period, tag['Value'], Statistic, Namespace,
                     Dimensions, sns_topic_arn)

    for tag in default_alarms[platform]:
        alarm_properties = tag['Key'].split('-')
        Namespace = alarm_properties[1]
        MetricName = alarm_properties[2]

        # if the custom alarm is from the standard AWS/EC2 metrics then set static dimensions.
        if Namespace == 'AWS/EC2':
            Dimensions = [{
                'Name': 'InstanceId',
                'Value': instance_id
            }]
        else:
            Dimensions = list()
            for dimension_name in append_dimensions:
                dimension = dict()

                if dimension_name == 'AutoScalingGroupName':
                    instance_asg = next(
                        (tag['Value'] for tag in instance_tags if tag['Key'] == 'aws:autoscaling:groupName'), None)
                    if instance_asg:
                        dimension_value = instance_asg
                        dimension['Name'] = dimension_name
                        dimension['Value'] = dimension_value
                else:
                    dimension_value = instance_info.get(dimension_name, None)
                    dimension['Name'] = dimension_name
                    dimension['Value'] = dimension_value

                Dimensions.append(dimension)

        additional_dimensions = metric_dimensions_map.get(MetricName, None)

        AlarmName = 'AutoAlarm-{}-{}'.format(instance_id, MetricName)
        properties_offset = 0
        if additional_dimensions:
            for pos, dim in enumerate(additional_dimensions, 1):
                Dimensions.append(
                    {
                        'Name': dim,
                        'Value': alarm_properties[(pos + 2)]
                    }
                )
                AlarmName = AlarmName + '-{}'.format(alarm_properties[(pos + 2)])
                properties_offset = properties_offset + 1

        ComparisonOperator = alarm_properties[(properties_offset + 3)]
        Period = alarm_properties[(properties_offset + 4)]
        Statistic = alarm_properties[(properties_offset + 5)]

        AlarmName = AlarmName + '-{}-{}-{}'.format(ComparisonOperator, tag['Value'], Period)

        create_alarm(AlarmName, MetricName, ComparisonOperator, Period, tag['Value'], Statistic, Namespace,
                     Dimensions, sns_topic_arn)


def determine_platform(imageid):
    try:
        ec2_client = boto3_client('ec2')
        # does instance have appropriate alarm tag?
        image_info = ec2_client.describe_images(
            ImageIds=[
                imageid
            ]

        )

        # can only be one instance when called by CloudWatch Events
        if 'Images' in image_info and len(image_info['Images']) > 0:
            platform_details = image_info['Images'][0]['PlatformDetails']
            logger.debug('Platform details of image: {}'.format(platform_details))
            if 'Windows' in platform_details or 'SQL Server' in platform_details:
                return 'Windows'
            elif 'Red Hat' in platform_details:
                return 'Red Hat'
            elif 'SUSE' in platform_details:
                return 'SUSE'
            elif 'Linux/UNIX' in platform_details:
                if 'ubuntu' in image_info['Images'][0]['Description'].lower() or 'ubuntu' in image_info['Images'][0][
                    'Name'].lower():
                    return 'Ubuntu'
                else:
                    return 'Amazon Linux'
            else:
                return None
        else:
            return None

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Failure describing image {}: {}'.format(imageid, e))
        raise


def convert_to_seconds(s):
    try:
        seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return int(s[:-1]) * seconds_per_unit[s[-1]]
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Error converting threshold string {} to seconds!'.format(s, e))
        raise


# Alarm Name Format: AutoAlarm-<InstanceId>-<Statistic>-<MetricName>-<ComparisonOperator>-<Threshold>-<Period>
# Example:  AutoAlarm-i-00e4f327736cb077f-CPUUtilization-GreaterThanThreshold-80-5m
def create_alarm(AlarmName, MetricName, ComparisonOperator, Period, Threshold, Statistic, Namespace, Dimensions,
                 sns_topic_arn):
    AlarmDescription = 'Alarm created by lambda function CloudWatchAutoAlarms'

    try:
        Period = convert_to_seconds(Period)
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error converting Period specified {} to seconds for Alarm {}!: {}'.format(Period, AlarmName, e))

    Threshold = float(Threshold)
    try:
        cw_client = boto3_client('cloudwatch')

        alarm = {
            'AlarmName': AlarmName,
            'AlarmDescription': AlarmDescription,
            'MetricName': MetricName,
            'Namespace': Namespace,
            'Dimensions': Dimensions,
            'Period': Period,
            'EvaluationPeriods': 1,
            'Threshold': Threshold,
            'ComparisonOperator': ComparisonOperator,
            'Statistic': Statistic
        }

        if sns_topic_arn is not None:
            alarm['AlarmActions'] = [sns_topic_arn]

        cw_client.put_metric_alarm(**alarm)

        logger.info('Created alarm {}'.format(AlarmName))

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error creating alarm {}!: {}'.format(AlarmName, e))


def delete_alarms(instance_id):
    try:
        AlarmNamePrefix = "AutoAlarm-{}".format(instance_id)
        cw_client = boto3_client('cloudwatch')
        logger.info('calling describe alarms with prefix {}'.format(AlarmNamePrefix))
        response = cw_client.describe_alarms(
            AlarmNamePrefix=AlarmNamePrefix,
        )
        alarm_list = []
        logger.info('Response from describe_alarms(): {}'.format(response))
        if 'MetricAlarms' in response:
            for alarm in response['MetricAlarms']:
                alarm_name = alarm['AlarmName']
                alarm_list.append(alarm_name)
        logger.info('deleting {} for instance {}'.format(alarm_list, instance_id))
        response = cw_client.delete_alarms(
            AlarmNames=alarm_list
        )
        return True
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error deleting alarms for instance {}!: {}'.format(instance_id, e))
