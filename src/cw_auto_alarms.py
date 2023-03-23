import logging
from actions import check_alarm_tag, process_alarm_tags, delete_alarms, process_lambda_alarms, \
    scan_and_process_alarm_tags
from os import getenv

logger = logging.getLogger()
log_level = getenv("LOGLEVEL", "INFO")
level = logging.getLevelName(log_level)
logger.setLevel(level)

create_alarm_tag = getenv("ALARM_TAG", "Create_Auto_Alarms")

cw_namespace = getenv("CLOUDWATCH_NAMESPACE", "CWAgent")

create_default_alarms_flag = getenv("CREATE_DEFAULT_ALARMS", "true").lower()

append_dimensions = getenv("CLOUDWATCH_APPEND_DIMENSIONS", 'InstanceId, ImageId, InstanceType')
append_dimensions = [dimension.strip() for dimension in append_dimensions.split(',')]

alarm_cpu_high_default_threshold = getenv("ALARM_CPU_HIGH_THRESHOLD", "75")
alarm_memory_high_default_threshold = getenv("ALARM_MEMORY_HIGH_THRESHOLD", "75")
alarm_disk_space_percent_free_threshold = getenv("ALARM_DISK_PERCENT_LOW_THRESHOLD", "20")
alarm_disk_used_percent_threshold = 100 - int(alarm_disk_space_percent_free_threshold)

alarm_lambda_error_threshold = getenv("ALARM_LAMBDA_ERROR_THRESHOLD", "1")
alarm_lambda_throttles_threshold = getenv("ALARM_LAMBDA_THROTTLE_THRESHOLD", "1")
alarm_lambda_dead_letter_error_threshold = getenv("ALARM_LAMBDA_DEAD_LETTER_ERROR_THRESHOLD", "1")
alarm_lambda_destination_delivery_failure_threshold = getenv("ALARM_LAMBDA_DESTINATION_DELIVERY_FAILURE_THRESHOLD", "1")

sns_topic_arn = getenv("DEFAULT_ALARM_SNS_TOPIC_ARN", None)

alarm_separator = '-'
alarm_identifier = getenv("ALARM_IDENTIFIER_PREFIX", 'AutoAlarm')

default_period = '5m'
default_evaluation_periods = '1'
default_statistic = 'Average'

# For Redhat, the default device is xvda2, xfs, for Ubuntu, the default fstype is ext4,
# for Amazon Linux, the default device is xvda1, xfs
default_alarms = {
    # default<number> added to the end of the key to  make the key unique
    # this differentiate alarms with similar settings but different thresholds
    'AWS/EC2': [
        {
            'Key': alarm_separator.join(
                [alarm_identifier, 'AWS/EC2', 'CPUUtilization', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
            'Value': alarm_cpu_high_default_threshold
        }
    ],
    'AWS/Lambda': [
        {
            'Key': alarm_separator.join(
                [alarm_identifier, 'AWS/Lambda', 'Errors', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
            'Value': alarm_lambda_error_threshold
        },
        {
            'Key': alarm_separator.join(
                [alarm_identifier, 'AWS/Lambda', 'Throttles', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
            'Value': alarm_lambda_throttles_threshold
        }
    ],
    cw_namespace: {
        'Windows': [

            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'LogicalDisk % Free Space', 'objectname', 'LogicalDisk',
                     'instance', 'C:', 'LessThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_disk_space_percent_free_threshold
            },
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'Memory % Committed Bytes In Use', 'objectname', 'Memory',
                     'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_memory_high_default_threshold
            }
        ],
        'Amazon Linux': [
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'disk_used_percent', 'device', 'xvda1', 'fstype', 'xfs', 'path',
                     '/', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_disk_used_percent_threshold
            },
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'mem_used_percent', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic,
                     'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_memory_high_default_threshold
            }
        ],
        'Red Hat': [
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'disk_used_percent', 'device', 'xvda2', 'fstype', 'xfs', 'path',
                     '/', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_disk_used_percent_threshold
            },
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'mem_used_percent', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic,
                     'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_memory_high_default_threshold
            }
        ],
        'Ubuntu': [
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'disk_used_percent', 'device', 'xvda1', 'fstype', 'ext4', 'path',
                     '/', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_disk_used_percent_threshold
            },
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'mem_used_percent', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic,
                     'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_memory_high_default_threshold
            }
        ],
        'SUSE': [
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'disk_used_percent', 'device', 'xvda1', 'fstype', 'xfs', 'path',
                     '/', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic, 'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_disk_used_percent_threshold
            },
            {
                'Key': alarm_separator.join(
                    [alarm_identifier, cw_namespace, 'mem_used_percent', 'GreaterThanThreshold', default_period, default_evaluation_periods, default_statistic,
                     'Created_by_CloudWatchAutoAlarms']),
                'Value': alarm_memory_high_default_threshold
            }
        ]
    }
}

metric_dimensions_map = {
    cw_namespace: append_dimensions,
    'AWS/EC2': ['InstanceId']
}


def lambda_handler(event, context):
    logger.info('event received: {}'.format(event))
    try:
        if 'source' in event and event['source'] == 'aws.ec2' and event['detail']['state'] == 'running':
            instance_id = event['detail']['instance-id']
            # determine if instance is tagged to create an alarm
            instance_info = check_alarm_tag(instance_id, create_alarm_tag)

            # instance has been tagged for alarming, confirm an alarm doesn't already exist
            if instance_info:
                process_alarm_tags(instance_id, instance_info, default_alarms, metric_dimensions_map, sns_topic_arn,
                                   cw_namespace, create_default_alarms_flag, alarm_separator, alarm_identifier)
        elif 'source' in event and event['source'] == 'aws.ec2' and event['detail']['state'] == 'terminated':
            instance_id = event['detail']['instance-id']
            result = delete_alarms(instance_id, alarm_identifier, alarm_separator)
        elif 'source' in event and event['source'] == 'aws.lambda' and event['detail'][
            'eventName'] == 'TagResource20170331v2':
            logger.debug(
                'Tag Lambda Function event occurred, tags are: {}'.format(event['detail']['requestParameters']['tags']))
            tags = event['detail']['requestParameters']['tags']
            function = event['detail']['requestParameters']['resource'].split(":")[-1]
            process_lambda_alarms(function, tags, create_alarm_tag, default_alarms, sns_topic_arn, alarm_separator, alarm_identifier)
        elif 'source' in event and event['source'] == 'aws.lambda' and event['detail'][
            'eventName'] == 'DeleteFunction20150331':
            function = event['detail']['requestParameters']['functionName']
            logger.debug('Delete Lambda Function event occurred for: {}'.format(function))
            result = delete_alarms(function, alarm_identifier, alarm_separator)
        elif 'action' in event and event['action'] == 'scan':
            logger.debug(
                f'Scanning for EC2 instances with tag: {create_alarm_tag} to create alarm'
            )
            scan_and_process_alarm_tags(create_alarm_tag, default_alarms, metric_dimensions_map, sns_topic_arn,
                                        cw_namespace, create_default_alarms_flag, alarm_separator, alarm_identifier)

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail the job and log the exception message.
        logger.error('Failure creating alarm: {}'.format(e))
        raise
