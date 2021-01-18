from datetime import datetime, timedelta
import logging
from actions import check_alarm_tag, process_alarm_tags, delete_alarms
from os import getenv

logger = logging.getLogger()

create_alarm_tag = getenv("ALARM_TAG", "Create_Auto_Alarms")

cw_namespace = getenv("CLOUDWATCH_NAMESPACE", "CWAgent")

append_dimensions = getenv("CLOUDWATCH_APPEND_DIMENSIONS", 'InstanceId, ImageId, InstanceType')
append_dimensions = [dimension.strip() for dimension in append_dimensions.split(',')]

alarm_cpu_high_default_threshold = getenv("ALARM_CPU_HIGH_THRESHOLD", "75")
alarm_credit_balance_low_default_threshold = getenv("ALARM_CPU_CREDIT_BALANCE_LOW_THRESHOLD", "100")
alarm_memory_high_default_threshold = getenv("ALARM_MEMORY_HIGH_THRESHOLD", "75")
alarm_disk_space_percent_free_threshold = getenv("ALARM_DISK_PERCENT_LOW_THRESHOLD", "20")
alarm_disk_used_percent_threshold = 100 - int(alarm_disk_space_percent_free_threshold)

sns_topic_arn = getenv("DEFAULT_ALARM_SNS_TOPIC_ARN", None)

# For Redhat, the default device is xvda2, xfs, for Ubuntu, the default fstype is ext4,
# for Amazon Linux, the default device is xvda1, xfs
default_alarms = {
    'All': [
        {
            'Key': 'AutoAlarm-AWS/EC2-CPUUtilization-GreaterThanThreshold-5m-Average',
            'Value': alarm_cpu_high_default_threshold
        },
        {
            'Key': 'AutoAlarm-AWS/EC2-CPUCreditBalance-LessThanThreshold-5m-Average',
            'Value': alarm_credit_balance_low_default_threshold
        }],
    'Windows': [

        {
            'Key': 'AutoAlarm-{}-LogicalDisk % Free Space-LogicalDisk-C:-LessThanThreshold-5m-Average'.format(
                cw_namespace),
            'Value': alarm_disk_space_percent_free_threshold
        },
        {
            'Key': 'AutoAlarm-{}-Memory % Committed Bytes In Use-Memory-GreaterThanThreshold-5m-Average'.format(
                cw_namespace),
            'Value': alarm_memory_high_default_threshold
        }
    ],
    'Amazon Linux': [
        {
            'Key': 'AutoAlarm-{}-disk_used_percent-xvda1-xfs-/-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_disk_used_percent_threshold
        },
        {
            'Key': 'AutoAlarm-{}-mem_used_percent-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_memory_high_default_threshold
        }
    ],
    'Red Hat': [
        {
            'Key': 'AutoAlarm-{}-disk_used_percent-xvda2-xfs-/-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_disk_used_percent_threshold
        },
        {
            'Key': 'AutoAlarm-{}-mem_used_percent-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_memory_high_default_threshold
        }
    ],
    'Ubuntu': [
        {
            'Key': 'AutoAlarm-{}-disk_used_percent-xvda1-ext4-/-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_disk_used_percent_threshold
        },
        {
            'Key': 'AutoAlarm-{}-mem_used_percent-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_memory_high_default_threshold
        }
    ],
    'SUSE': [
        {
            'Key': 'AutoAlarm-{}-disk_used_percent-xvda1-xfs-/-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_disk_used_percent_threshold
        },
        {
            'Key': 'AutoAlarm-{}-mem_used_percent-GreaterThanThreshold-5m-Average'.format(cw_namespace),
            'Value': alarm_memory_high_default_threshold
        }
    ]
}

metric_dimensions_map = {
    'mem_used_percent': [],
    'disk_used_percent': ['device', 'fstype', 'path'],
    'Memory % Committed Bytes In Use': ['objectname'],
    'LogicalDisk % Free Space': ['objectname', 'instance']
}



'''
Process EC2 state change notifications when instance is running (sample event):

{
    "version": "0",
    "id": "ee376907-2647-4179-9203-343cfb3017a4",
    "detail-type": "EC2 Instance State-change Notification",
    "source": "aws.ec2",
    "account": "123456789012",
    "time": "2015-11-11T21:30:34Z",
    "region": "us-east-1",
    "resources": [
        "arn:aws:ec2:us-east-1:123456789012:instance/i-abcd1111"
    ],
    "detail": {
        "instance-id": "i-0078bdfee966f18ec",
        "state": "running"
    }
}

'''


def lambda_handler(event, context):
    logger.info('event received: {}'.format(event))
    try:
        if 'source' in event and event['source'] == 'aws.ec2' and event['detail']['state'] == 'running':
            instance_id = event['detail']['instance-id']
            # determine if instance is tagged to create an alarm
            instance_info = check_alarm_tag(instance_id, create_alarm_tag)

            # instance has been tagged for alarming, confirm an alarm doesn't already exist
            if instance_info:
                process_alarm_tags(instance_id, instance_info, default_alarms, metric_dimensions_map, sns_topic_arn, append_dimensions,
                                   cw_namespace)
        elif 'source' in event and event['source'] == 'aws.ec2' and event['detail']['state'] == 'terminated':
            instance_id = event['detail']['instance-id']
            result = delete_alarms(instance_id)

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail the job and log the exception message.
        logger.error('Failure creating alarm for instance {}: {}'.format(instance_id, e))
        raise
