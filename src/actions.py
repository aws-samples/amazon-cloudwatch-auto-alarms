import boto3
import logging
from botocore.config import Config
from os import getenv
from datetime import datetime

logger = logging.getLogger()
log_level = getenv("LOGLEVEL", "INFO")
level = logging.getLevelName(log_level)
logger.setLevel(level)

valid_comparators = ['GreaterThanOrEqualToThreshold', 'GreaterThanThreshold', 'LessThanThreshold',
                     'LessThanOrEqualToThreshold', "LessThanLowerOrGreaterThanUpperThreshold", "LessThanLowerThreshold",
                     "GreaterThanUpperThreshold"]

valid_anomaly_detection_comparators = ["LessThanLowerOrGreaterThanUpperThreshold", "LessThanLowerThreshold",
                                       "GreaterThanUpperThreshold"]

valid_statistics = ['Average', 'SampleCount', 'Sum', 'Minimum', 'Maximum']


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


def get_tags_for_rds_instance(db_instance_arn):
    try:
        rds_client = boto3_client('rds')
        response = rds_client.list_tags_for_resource(
            ResourceName=db_instance_arn,
        )

        return response.get('TagList', None)

    except Exception as e:
        logger.error('Getting dimensions: {}'.format(e))
        raise


def process_rds_alarms(db_arn, is_cluster, activation_tag, default_alarms, sns_topic_arn, alarm_separator,
                       alarm_identifier, tags):
    activation_tag = [{'Key': activation_tag} for tag in tags if tag.get("key", None) == activation_tag]
    if not len(activation_tag) > 0:
        logger.debug('Activation tag not found for {}, nothing to do'.format(db_arn))
        return True
    else:
        logger.debug('Processing db specific custom alarms for: {}'.format(db_arn))
        for tag in tags:
            if tag["key"].startswith(alarm_identifier):
                logger.info('Alarm identifier found: processing db specific alarms for: {}'.format(
                    db_arn))
                default_alarms['AWS/RDS'].append({'Key': tag["key"], 'Value': tag.get("value", "")})

    # set the default dimensions for AWS/RDS
    db_id = db_arn.split(':')[-1]
    dimensions = list()

    if is_cluster:
        dimensions.append(
            {
                'Name': 'DBClusterIdentifier',
                'Value': db_id
            }
        )
    else:
        dimensions.append(
            {
                'Name': 'DBInstanceIdentifier',
                'Value': db_id
            }
        )

    for tag in default_alarms['AWS/RDS']:
        alarm_properties = tag['Key'].split(alarm_separator)
        Namespace = alarm_properties[1]
        MetricName = alarm_properties[2]
        ComparisonOperator = alarm_properties[3]
        Period = alarm_properties[4]
        EvaluationPeriods = alarm_properties[5]
        Statistic = alarm_properties[6]

    AlarmName = alarm_separator.join(
        [alarm_identifier, db_id, Namespace, MetricName, ComparisonOperator, str(tag['Value']),
         Period, "{}p".format(EvaluationPeriods), Statistic])

    # capture optional alarm description
    try:
        AlarmDescription = alarm_properties[7]
        AlarmName += alarm_separator + AlarmDescription
    except:
        logger.info('Description not supplied')
        AlarmDescription = None

    create_alarm(AlarmName, AlarmDescription, MetricName, ComparisonOperator, Period, tag['Value'], Statistic,
                 Namespace, dimensions, EvaluationPeriods, sns_topic_arn)


def process_lambda_alarms(function_name, tags, activation_tag, default_alarms, sns_topic_arn, alarm_separator,
                          alarm_identifier):
    activation_tag = tags.get(activation_tag, 'not_found')
    if activation_tag == 'not_found':
        logger.debug('Activation tag not found for {}, nothing to do'.format(function_name))
        return True
    else:
        logger.debug('Processing function specific alarms for: {}'.format(function_name))
        for tag_key in tags:
            if tag_key.startswith(alarm_identifier):
                default_alarms['AWS/Lambda'].append({'Key': tag_key, 'Value': tags[tag_key]})

        # get the default dimensions for AWS/EC2
        dimensions = list()
        dimensions.append(
            {
                'Name': 'FunctionName',
                'Value': function_name
            }
        )

        for tag in default_alarms['AWS/Lambda']:
            alarm_properties = tag['Key'].split(alarm_separator)
            Namespace = alarm_properties[1]
            MetricName = alarm_properties[2]
            ComparisonOperator = alarm_properties[3]
            Period = alarm_properties[4]

            # Provide support for previous formatting of custom alarm tags where the evaluation period wasn't specified.
            # If an evaluation period isn't specified in the tag then it defaults to 1, similar to past behavior.
            if alarm_properties[5] in valid_statistics:
                EvaluationPeriods = 1
                eval_period_offset = 0
            else:
                EvaluationPeriods = alarm_properties[5]
                eval_period_offset = 1

            Statistic = alarm_properties[(5 + eval_period_offset)]

            AlarmName = alarm_separator.join(
                [alarm_identifier, function_name, Namespace, MetricName, ComparisonOperator, str(tag['Value']),
                 Period, "{}p".format(EvaluationPeriods), Statistic])

            # capture optional alarm description
            try:
                AlarmDescription = alarm_properties[(6 + eval_period_offset)]
                AlarmName += alarm_separator + AlarmDescription
            except:
                logger.info('Description not supplied')
                AlarmDescription = None

            create_alarm(AlarmName, AlarmDescription, MetricName, ComparisonOperator, Period, tag['Value'], Statistic,
                         Namespace,
                         dimensions, EvaluationPeriods, sns_topic_arn)


# def create_alarm_from_wildcard_tag(instance_id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
#                                    alarm_separator, alarm_identifier):
#     alarm_properties = alarm_tag['Key'].split(alarm_separator)
#     namespace = alarm_properties[1]
#     MetricName = alarm_properties[2]
#     AlarmName = alarm_separator.join([alarm_identifier, id, namespace, MetricName])
#
#     dimensions, properties_offset, AlarmName = determine_dimensions(AlarmName, alarm_separator, alarm_tag, instance_info, metric_dimensions_map,
#                                                                     namespace)

def create_alarm_from_tag(id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn, alarm_separator,
                          alarm_identifier):
    # split alarm tag to decipher alarm properties, first property is alarm_identifier and ignored...
    alarm_properties = alarm_tag['Key'].split(alarm_separator)
    namespace = alarm_properties[1]
    MetricName = alarm_properties[2]

    AlarmName = alarm_separator.join([alarm_identifier, id, namespace, MetricName])

    dimensions, properties_offset, AlarmName = determine_dimensions(AlarmName, alarm_separator, alarm_tag,
                                                                    instance_info, metric_dimensions_map,
                                                                    namespace)

    logger.info("dimensions: {}, properties_offset: {}, AlarmName: {}".format(dimensions, properties_offset, AlarmName))
    ComparisonOperator = alarm_properties[(properties_offset + 3)]
    Period = alarm_properties[(properties_offset + 4)]

    # Provide support for previous formatting of custom alarm tags where the evaluation period wasn't specified.
    # If an evaluation period isn't specified in the tag then it defaults to 1, similar to past behavior.
    if alarm_properties[(properties_offset + 5)] in valid_statistics:
        EvaluationPeriods = 1
        eval_period_offset = 0
    else:
        EvaluationPeriods = alarm_properties[(properties_offset + 5)]
        eval_period_offset = 1

    Statistic = alarm_properties[(properties_offset + 5 + eval_period_offset)]

    AlarmName += alarm_separator.join(
        ['', ComparisonOperator, str(alarm_tag['Value']), str(Period), "{}p".format(EvaluationPeriods), Statistic])

    # add the description to the alarm name. If none are specified, log a message
    try:
        AlarmDescription = alarm_properties[(properties_offset + 6 + eval_period_offset)]
        AlarmName += alarm_separator + AlarmDescription
    except:
        logger.info('Description not supplied')
        AlarmDescription = None

    create_alarm(AlarmName, AlarmDescription, MetricName, ComparisonOperator, Period, alarm_tag['Value'], Statistic,
                 namespace,
                 dimensions, EvaluationPeriods, sns_topic_arn)


def determine_dimensions(AlarmName, alarm_separator, alarm_tag, instance_info, metric_dimensions_map, namespace):
    dimensions = list()
    # the number of dimensions may be different depending on the namespace.  For the default 'CWAgent' namespace, the default is to also include extended properties defined in cw_auto_alarms.py:append_dimensions
    for dimension_name in metric_dimensions_map.get(namespace, list()):
        dimension = dict()
        # Evaluate the dimensions specified for the metric namespace
        # If AutoScalingGroupName has been specified as a dimension to include, we first check to see if the instance has a tag indicating it is a part of an ASG.
        # If it is, we get the ASG name and populate its value for this dimension.
        if dimension_name == 'AutoScalingGroupName':
            # find out if the instance is part of an autoscaling group
            instance_asg = next(
                (tag['Value'] for tag in instance_info['Tags'] if tag['Key'] == 'aws:autoscaling:groupName'), None)
            if instance_asg:
                dimension_value = instance_asg
                dimension['Name'] = dimension_name
                dimension['Value'] = dimension_value
                dimensions.append(dimension)
        else:
            # If the dimension exists as a property of the EC2 instance being processed, get the dimension value from
            # the EC2 instance details and add, otherwise issue a warning and skip.
            dimension_value = instance_info.get(dimension_name, None)
            if dimension_value:
                dimension['Name'] = dimension_name
                dimension['Value'] = dimension_value
                dimensions.append(dimension)
            else:
                logger.warning(
                    "Dimension {} has been specified in APPEND_DIMENSIONS but  no dimension value exists, skipping...".format(
                        dimension_name))
    logger.debug("dimensions are {}".format(dimensions))
    additional_dimensions = determine_additional_dimensions(alarm_tag, alarm_separator)
    # process the dimensions
    properties_offset = 0
    try:
        if additional_dimensions:
            for num, dim in enumerate(additional_dimensions[::2]):
                val = additional_dimensions[num * 2 + 1]
                dimensions.append(
                    {
                        'Name': dim,
                        'Value': val
                    }
                )
                AlarmName += alarm_separator.join(['', dim, val])
                properties_offset = properties_offset + 2
    except Exception as e:
        logger.error('Getting dimensions: {}'.format(e))
        raise

    return dimensions, properties_offset, AlarmName


def determine_additional_dimensions(alarm_tag, alarm_separator):
    alarm_properties = alarm_tag['Key'].split(alarm_separator)
    additional_dimensions = list()
    # determine the dimensions and the last dimension for this alarm
    # exclude last element which is the DESCRIPTION that differentiates alarms
    for index, prop in enumerate(alarm_properties[3:-1], start=3):
        if prop in valid_comparators:
            prop_end_index = index
            break
    else:
        prop_end_index = None
    if prop_end_index:
        additional_dimensions.extend(alarm_properties[3:prop_end_index])
    else:
        logger.error('Unable to determine the dimensions for alarm tag: {}'.format(alarm_tag))
        raise Exception
    return additional_dimensions


def process_alarm_tags(instance_id, instance_info, default_alarms, wildcard_alarms, metric_dimensions_map,
                       sns_topic_arn, cw_namespace,
                       create_default_alarms_flag, alarm_separator, alarm_identifier):
    tags = instance_info['Tags']

    ImageId = instance_info['ImageId']
    logger.debug('ImageId is: {}'.format(ImageId))
    platform = determine_platform(ImageId)

    # if platform information is unavailable via determine_platform, try the platform in instance_info
    # determine_platform uses the describe_images API call. In some cases, the AMI may be deregistered
    # hence, use instance_info to extract platform details. This can detect Windows, Red Hat, SUSE platforms
    # instance_info does not contain enough information to distinguish Ubuntu and Amazon Linux platforms

    if not platform:
        platform_details = instance_info['PlatformDetails']
        logger.debug('Platform details of instance: {}'.format(platform_details))
        platform = format_platform_details(platform_details)

    logger.debug('Platform is: {}'.format(platform))

    # scan instance tags and create alarms for any custom alarm tags
    for instance_tag in tags:
        if instance_tag['Key'].startswith(alarm_identifier):
            create_alarm_from_tag(instance_id, instance_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                  alarm_separator, alarm_identifier)

    if create_default_alarms_flag == 'true':
        for alarm_tag in default_alarms['AWS/EC2']:
            create_alarm_from_tag(instance_id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                  alarm_separator, alarm_identifier)
        if platform:
            for alarm_tag in default_alarms[cw_namespace][platform]:
                create_alarm_from_tag(instance_id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                      alarm_separator, alarm_identifier)
            if wildcard_alarms and cw_namespace in wildcard_alarms and platform in wildcard_alarms[cw_namespace]:
                for wildcard_alarm_tag in wildcard_alarms[cw_namespace][platform]:
                    logger.info("processing wildcard tag {}".format(wildcard_alarm_tag))
                    resolved_alarm_tags = determine_wildcard_alarms(wildcard_alarm_tag, alarm_separator,
                                                                    instance_info, metric_dimensions_map)
                    if resolved_alarm_tags:
                        for resolved_alarm_tag in resolved_alarm_tags:
                            create_alarm_from_tag(instance_id, resolved_alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                                  alarm_separator, alarm_identifier)
                    else:
                        logger.info("No wildcard alarms found for platform: {}".format(platform))
        else:
            logger.warning("Skipping platform specific alarm creation for {}, unknown platform.".format(instance_id))
    else:
        logger.info("Default alarm creation is turned off")


def determine_wildcard_alarms(wildcard_alarm_tag, alarm_separator, instance_info, metric_dimensions_map):
    fixed_alarm_tags = []
    alarm_properties = wildcard_alarm_tag['Key'].split(alarm_separator)
    namespace = alarm_properties[1]
    MetricName = alarm_properties[2]

    dimensions, properties_offset, AlarmName = determine_dimensions("", alarm_separator, wildcard_alarm_tag,
                                                                    instance_info, metric_dimensions_map,
                                                                    namespace)
    logger.info("wildcard alarm: {}, dimensions: {}, properties offset: {}".format(wildcard_alarm_tag, dimensions,
                                                                                   properties_offset))

    wildcard_dimensions = [dimension for dimension in dimensions if dimension['Value'] == '*']
    fixed_dimensions = [dimension for dimension in dimensions if dimension['Value'] != '*']

    logger.info("original dimensions: ${}, wildcard_dimensions: {},\nfixed_dimensions: {}".format(dimensions,wildcard_dimensions, fixed_dimensions))

    cw_client = boto3_client('cloudwatch')
    listmetrics_response = cw_client.list_metrics(
        Namespace=namespace,
        MetricName=MetricName,
        Dimensions=fixed_dimensions,
        # IncludeLinkedAccounts=False,
        # OwningAccount='string'
    )

    logger.info("list_metrics response: {}".format(listmetrics_response))

    metrics_for_wildcards = None
    if 'Metrics' in listmetrics_response:
        metrics_for_wildcards = listmetrics_response['Metrics']
        for metric in metrics_for_wildcards:
            translated_alarm = dict()
            original_alarm_key = alarm_properties.copy()
            metric_dimensions = metric['Dimensions']
            for wildcard_dim in wildcard_dimensions:
                wildcard_dim['Name']
                for metric_dim in metric_dimensions:
                    if metric_dim['Name'] == wildcard_dim['Name']:
                        original_dim_value_index = original_alarm_key.index(metric_dim['Name']) + 1
                        original_alarm_key[original_dim_value_index] = metric_dim['Value']

            translated_alarm['Key'] = alarm_separator.join(original_alarm_key)
            translated_alarm['Value'] = wildcard_alarm_tag['Value']
            fixed_alarm_tags.append(translated_alarm)

    logger.info("fixed alarm tags are: {}".format(fixed_alarm_tags))
    return fixed_alarm_tags











        # {
        #     'Key': alarm_separator.join(
        #         [alarm_identifier, cw_namespace, 'LogicalDisk % Free Space', 'objectname', 'LogicalDisk',
        #          'instance', 'C:', 'LessThanThreshold', default_period, default_evaluation_periods,
        #          default_statistic, 'Created_by_CloudWatchAutoAlarms']),
        #     'Value': alarm_disk_space_percent_free_threshold
        # },





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
            platform = format_platform_details(platform_details)
            if not platform and 'Linux/UNIX' in platform_details:
                if 'ubuntu' in image_info['Images'][0]['Name'].lower():
                    platform = 'Ubuntu'
                elif 'Description' in image_info['Images'][0] and 'ubuntu' in image_info['Images'][0][
                    'Description'].lower():
                    platform = 'Ubuntu'
                else:
                    # an assumption is made here that it is Amazon Linux.
                    # note that it could still be an Ubuntu EC2 instance if the AMI is an Ubuntu image
                    # but the Name and Description does not contain 'ubuntu'
                    platform = 'Amazon Linux'
            return platform
        else:
            return None

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Failure describing image {}: {}'.format(imageid, e))
        raise


def format_platform_details(platform_details):
    if 'Windows' in platform_details or 'SQL Server' in platform_details:
        return 'Windows'
    elif 'Red Hat' in platform_details:
        return 'Red Hat'
    elif 'SUSE' in platform_details:
        return 'SUSE'
    # don't handle the Linux/UNIX case in this common function because
    # instance_info does not have Description and Name unlike image_info
    # hence, if the AMI is no longer available and the EC2 is an Amazon Linux or Ubuntu instance,
    # return None which causes the Alarm creation to fail in this specific scenario

    # elif 'Linux/UNIX' in platform_details:
    #     if 'ubuntu' in image_info['Images'][0]['Description'].lower() or 'ubuntu' in image_info['Images'][0]['Name'].lower():
    #         return 'Ubuntu'
    #     else:
    #         return 'Amazon Linux'
    else:
        return None


def convert_to_seconds(s):
    try:
        seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return int(s[:-1]) * seconds_per_unit[s[-1]]
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Error converting threshold string {} to seconds!'.format(s, e))
        raise


# Alarm Name Format: <AlarmIdentifier>-<InstanceId>-<Namespace>-<MetricName>-<ComparisonOperator>-<Threshold>-<Period>-<EvaluationPeriods>p-<Statistic>
# Example:  AutoAlarm-i-00e4f327736cb077f-AWS/EC2_CPUUtilization-GreaterThanThreshold-80-5m-1p=Average
def create_alarm(AlarmName, AlarmDescription, MetricName, ComparisonOperator, Period, Threshold, Statistic, Namespace,
                 Dimensions,
                 EvaluationPeriods,
                 sns_topic_arn):
    if AlarmDescription:
        AlarmDescription = AlarmDescription.replace("_", " ")
    else:
        AlarmDescription = 'Created by cloudwatch-auto-alarms'

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

        metrics = [{
            'Id': 'm1',
            'MetricStat': {
                'Metric': {
                    'MetricName': MetricName,
                    'Namespace': Namespace,
                    'Dimensions': Dimensions
                },
                'Stat': Statistic,
                'Period': Period
            },
        }]

        alarm = {
            'AlarmName': AlarmName,
            'AlarmDescription': AlarmDescription,
            'EvaluationPeriods': int(EvaluationPeriods),
            'ComparisonOperator': ComparisonOperator,
            'Metrics': metrics
        }

        if ComparisonOperator in valid_anomaly_detection_comparators:
            metrics.append(
                {
                    'Id': 't1',
                    'Label': 't1',
                    'Expression': "ANOMALY_DETECTION_BAND(m1, {})".format(Threshold),
                }
            )
            alarm['ThresholdMetricId'] = 't1'
        else:
            alarm['Threshold'] = Threshold

        if sns_topic_arn and sns_topic_arn != '':
            alarm['AlarmActions'] = [sns_topic_arn]

        cw_client.put_metric_alarm(**alarm)

        logger.info('Created alarm {}'.format(AlarmName))

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error creating alarm {}!: {}'.format(AlarmName, e))


def delete_alarms(name, alarm_identifier, alarm_separator):
    try:
        AlarmNamePrefix = alarm_separator.join([alarm_identifier, name])
        AlarmNamePrefix += alarm_separator
        cw_client = boto3_client('cloudwatch')
        logger.debug('calling describe alarms with prefix {}'.format(AlarmNamePrefix))
        response = cw_client.describe_alarms(
            AlarmNamePrefix=AlarmNamePrefix,
        )
        alarm_list = []
        logger.debug('Response from describe_alarms(): {}'.format(response))
        if 'MetricAlarms' in response:
            for alarm in response['MetricAlarms']:
                alarm_name = alarm['AlarmName']
                alarm_list.append(alarm_name)
        if alarm_list:
            logger.info('deleting {} for {}'.format(alarm_list, name))
            cw_client.delete_alarms(
                AlarmNames=alarm_list
            )
        return True
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error deleting alarms for {}!: {}'.format(name, e))


def scan_and_process_alarm_tags(create_alarm_tag, default_alarms, metric_dimensions_map, sns_topic_arn,
                                cw_namespace, create_default_alarms_flag, alarm_separator, alarm_identifier):
    try:
        ec2_client = boto3_client('ec2')
        default_filtered_alarms, wildcard_alarms = separate_wildcard_alarms(alarm_separator, cw_namespace,
                                                                            default_alarms)
        for reservation in ec2_client.describe_instances()["Reservations"]:
            for instance in reservation["Instances"]:
                # Look for running instances only
                if instance["State"]["Code"] > 16:
                    continue
                if check_alarm_tag(instance["InstanceId"], create_alarm_tag):
                    process_alarm_tags(instance["InstanceId"], instance, default_filtered_alarms, wildcard_alarms,
                                       metric_dimensions_map,
                                       sns_topic_arn, cw_namespace, create_default_alarms_flag, alarm_separator,
                                       alarm_identifier)

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error('Failure describing reservations : {}'.format(e))
        raise


def separate_wildcard_alarms(alarm_separator, cw_namespace, default_alarms):
    wildcard_alarms = dict()
    wildcard_alarms[cw_namespace] = dict()
    for platform in default_alarms[cw_namespace]:
        wildcard_alarms[cw_namespace][platform] = list()
        logger.info("default alarms for {} are {}".format(platform, default_alarms[cw_namespace][platform]))
        wildcard_alarms[cw_namespace][platform] = [alarm for alarm in default_alarms[cw_namespace][platform] if
                                                   '*' in alarm['Key'].split(alarm_separator)]
        default_alarms[cw_namespace][platform] = [alarm for alarm in default_alarms[cw_namespace][platform] if
                                                  '*' not in alarm['Key'].split(alarm_separator)]
    logger.info("updated default alarms are {}".format(default_alarms[cw_namespace]))
    logger.info("updated wildcard alarms are {}".format(wildcard_alarms[cw_namespace]))
    return default_alarms, wildcard_alarms


def process_wildcard_alarm(alarm_object):
    print("alarm object is {}".format(alarm_object))
    alarm_object['Key'] = "updated"
    return alarm_object
