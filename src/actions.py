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


def boto3_client(resource, region, assumed_credentials=None):
    config = Config(
        retries=dict(
            max_attempts=40
        ),
        region_name=region
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

def get_current_account_id():
    sts_client = boto3_client('sts')

    # Call the `get_caller_identity` API
    account_id = sts_client.get_caller_identity()["Account"]

    # Print or return the account ID
    print(f"Account ID: {account_id}")
    return account_id


def assume_cross_account_role(account_id, region):
    """
    Assumes a cross-account role using the provided account ID and the global role name.
    If the role is unable to be assumed for any reason, returns None and logs an error message.
    """
    try:
        sts_client = boto3.client('sts', region_name=region)
        role_arn = f"arn:aws:iam::{account_id}:role/CloudWatchAutoAlarmCrossAccountRole"
        role_session_name = "CloudWatchAutoAlarmCrossAccountSession"

        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=role_session_name
        )
        return response['Credentials']
    except Exception as e:
        error_message = f"Failed to assume role {role_arn} in region {region}: {e}"
        logger.error(error_message)
        raise Exception(error_message)

def assume_management_account_role(account_id, region):
    """
    Assumes a cross-account role using the provided account ID and the global role name.
    If the role is unable to be assumed for any reason, returns None and logs an error message.
    """
    try:
        sts_client = boto3.client('sts', region_name=region)
        role_arn = f"arn:aws:iam::{account_id}:role/CloudWatchAutoAlarmManagementAccountRole"
        role_session_name = "CloudWatchAutoAlarmManagementAccountSession"

        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=role_session_name
        )
        return response['Credentials']
    except Exception as e:
        error_message = f"Failed to assume role {role_arn} in region {region}: {e}"
        logger.error(error_message)
        raise Exception(error_message)


def check_alarm_tag(instance_id, tag_key, region, account_id=None):
    """
    Checks for a specific tag on an EC2 instance. If an account ID is provided,
    assumes a cross-account role to access the EC2 client.
    """
    try:
        if account_id:
            logger.info("Using cross-account role for EC2 client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            ec2_client = boto3_client('ec2', region, assumed_credentials)
        else:
            logger.info("Using default credentials for EC2 client.")
            ec2_client = boto3_client('ec2', region)

        # Check if the instance has the appropriate alarm tag
        instance = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'tag-key',
                    'Values': [tag_key]
                }
            ],
            InstanceIds=[instance_id]
        )

        # Can only be one instance when called by CloudWatch Events
        if 'Reservations' in instance and len(instance['Reservations']) > 0 and len(
                instance['Reservations'][0]['Instances']) > 0:
            ec2_client.create_tags(
                Resources=[instance_id],
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
        # If any unexpected exceptions occur, log and raise the exception
        logger.error('Failure describing instance {} with tag key: {} : {}'.format(instance_id, tag_key, e))
        raise


def get_tags_for_rds_instance(db_instance_arn, region, account_id=None):
    """
    Retrieves the tags for a specified RDS instance. If an account ID is provided,
    assumes a cross-account role to access the RDS client.
    """
    try:
        if account_id:
            logger.info("Using cross-account role for RDS client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            rds_client = boto3_client('rds', region, assumed_credentials)
        else:
            logger.info("Using default credentials for RDS client.")
            rds_client = boto3_client('rds', region)

        response = rds_client.list_tags_for_resource(
            ResourceName=db_instance_arn,
        )

        return response.get('TagList', None)

    except Exception as e:
        logger.error('Error retrieving tags for RDS instance {}: {}'.format(db_instance_arn, e))
        raise


def process_rds_alarms(db_arn, is_cluster, activation_tag, default_alarms, sns_topic_arn, alarm_separator,
                       alarm_identifier, tags, region, account_id=None):
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
                 Namespace, dimensions, EvaluationPeriods, sns_topic_arn, region, account_id)


def process_lambda_alarms(function_name, tags, activation_tag, default_alarms, sns_topic_arn, alarm_separator,
                          alarm_identifier, region, account_id=None):
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
                         dimensions, EvaluationPeriods, sns_topic_arn, region, account_id)


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
                          alarm_identifier, region, account_id = None):
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
                 dimensions, EvaluationPeriods, sns_topic_arn, region, account_id)


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
                       sns_topic_arn, cw_namespace, create_default_alarms_flag, alarm_separator, alarm_identifier,
                       region, account_id=None):
    tags = instance_info['Tags']

    ImageId = instance_info['ImageId']
    logger.debug('ImageId is: {}'.format(ImageId))
    platform = determine_platform(ImageId, region, account_id)

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
                                  alarm_separator, alarm_identifier, region, account_id)

    if create_default_alarms_flag == 'true':
        for alarm_tag in default_alarms['AWS/EC2']:
            create_alarm_from_tag(instance_id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                  alarm_separator, alarm_identifier, region, account_id)
        if platform:
            for alarm_tag in default_alarms[cw_namespace][platform]:
                create_alarm_from_tag(instance_id, alarm_tag, instance_info, metric_dimensions_map, sns_topic_arn,
                                      alarm_separator, alarm_identifier, region, account_id)
            if wildcard_alarms and cw_namespace in wildcard_alarms and platform in wildcard_alarms[cw_namespace]:
                for wildcard_alarm_tag in wildcard_alarms[cw_namespace][platform]:
                    logger.info("processing wildcard tag {}".format(wildcard_alarm_tag))
                    resolved_alarm_tags = determine_wildcard_alarms(wildcard_alarm_tag, alarm_separator,
                                                                    instance_info, metric_dimensions_map, region, account_id)
                    if resolved_alarm_tags:
                        for resolved_alarm_tag in resolved_alarm_tags:
                            create_alarm_from_tag(instance_id, resolved_alarm_tag, instance_info, metric_dimensions_map,
                                                  sns_topic_arn,
                                                  alarm_separator, alarm_identifier, region, account_id)
                    else:
                        logger.info("No wildcard alarms found for platform: {}".format(platform))
        else:
            logger.warning("Skipping platform specific alarm creation for {}, unknown platform.".format(instance_id))
    else:
        logger.info("Default alarm creation is turned off")


def determine_wildcard_alarms(wildcard_alarm_tag, alarm_separator, instance_info, metric_dimensions_map,
                              region, account_id=None):
    """
    Determines fixed alarm tags for wildcard alarms, using cross-account permissions if an account ID is provided.
    """
    try:
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

        logger.info("original dimensions: {}, wildcard_dimensions: {}, fixed_dimensions: {}".format(
            dimensions, wildcard_dimensions, fixed_dimensions
        ))

        # Use cross-account role if account_id is provided
        if account_id:
            logger.info("Using cross-account role for CloudWatch client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            cw_client = boto3_client('cloudwatch', region, assumed_credentials)
        else:
            logger.info("Using default credentials for CloudWatch client.")
            cw_client = boto3_client('cloudwatch', region)

        listmetrics_response = cw_client.list_metrics(
            Namespace=namespace,
            MetricName=MetricName,
            Dimensions=fixed_dimensions
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
                    for metric_dim in metric_dimensions:
                        if metric_dim['Name'] == wildcard_dim['Name']:
                            original_dim_value_index = original_alarm_key.index(metric_dim['Name']) + 1
                            original_alarm_key[original_dim_value_index] = metric_dim['Value']

                translated_alarm['Key'] = alarm_separator.join(original_alarm_key)
                translated_alarm['Value'] = wildcard_alarm_tag['Value']
                fixed_alarm_tags.append(translated_alarm)

        logger.info("fixed alarm tags are: {}".format(fixed_alarm_tags))
        return fixed_alarm_tags

    except Exception as e:
        logger.error('Error determining wildcard alarms: {}'.format(e))
        raise


def determine_platform(imageid, region, account_id=None):
    """
    Determines the platform of an EC2 instance based on its AMI image ID.
    If an account ID is provided, assumes a cross-account role to access the EC2 client.
    """
    try:
        # Use cross-account role if account_id is provided
        if account_id:
            logger.info("Using cross-account role for EC2 client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            ec2_client = boto3_client('ec2', region, assumed_credentials)
        else:
            logger.info("Using default credentials for EC2 client.")
            ec2_client = boto3_client('ec2', region)

        # Retrieve image information
        image_info = ec2_client.describe_images(
            ImageIds=[imageid]
        )

        # Process the image information to determine the platform
        if 'Images' in image_info and len(image_info['Images']) > 0:
            platform_details = image_info['Images'][0].get('PlatformDetails', '')
            logger.debug('Platform details of image: {}'.format(platform_details))
            platform = format_platform_details(platform_details)

            if not platform and 'Linux/UNIX' in platform_details:
                image_name = image_info['Images'][0].get('Name', '').lower()
                description = image_info['Images'][0].get('Description', '').lower()
                if 'ubuntu' in image_name:
                    platform = 'Ubuntu'
                elif 'ubuntu' in description:
                    platform = 'Ubuntu'
                else:
                    # an assumption is made here that it is Amazon Linux.
                    # note that it could still be an Ubuntu EC2 instance if the AMI is an Ubuntu image
                    # but the Name and Description does not contain 'ubuntu'
                    platform = 'Amazon Linux'
            return platform
        else:
            logger.warning("No image information found for ImageId: {}".format(imageid))
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
                 sns_topic_arn, region, account_id = None):
    if AlarmDescription:
        AlarmDescription = AlarmDescription.replace("_", " ")
    else:
        AlarmDescription = 'Created by cloudwatch-auto-alarms'

    try:
        Period = convert_to_seconds(Period)
    except Exception as e:
        logger.error(
            'Error converting Period specified {} to seconds for Alarm {}!: {}'.format(Period, AlarmName, e))
        raise

    Threshold = float(Threshold)

    logger.info("Creating alarm in region {}, account {}".format(region, account_id))
    try:
        # Use cross-account role if account_id is provided
        if account_id:
            logger.info("Using cross-account role for CloudWatch client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            cw_client = boto3_client('cloudwatch', region, assumed_credentials)
        else:
            logger.info("Using default credentials for CloudWatch client.")
            cw_client = boto3_client('cloudwatch', region)

        # Define the metrics for the alarm
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

        # Define the alarm
        alarm = {
            'AlarmName': AlarmName,
            'AlarmDescription': AlarmDescription,
            'EvaluationPeriods': int(EvaluationPeriods),
            'ComparisonOperator': ComparisonOperator,
            'Metrics': metrics
        }

        # Handle anomaly detection comparators
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

        # Add SNS topic for notifications
        if sns_topic_arn is not None:
            alarm['AlarmActions'] = [sns_topic_arn]

        # Create the alarm
        cw_client.put_metric_alarm(**alarm)
        logger.info('Created alarm {}'.format(AlarmName))

    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail and log the exception message.
        logger.error(
            'Error creating alarm {}!: {}'.format(AlarmName, e))


def delete_alarms(name, alarm_identifier, alarm_separator, region, account_id=None):
    """
    Deletes CloudWatch alarms matching the specified name and alarm identifier.
    If an account ID is provided, assumes a cross-account role to access the CloudWatch client.
    """
    try:
        AlarmNamePrefix = alarm_separator.join([alarm_identifier, name]) + alarm_separator

        # Use cross-account role if account_id is provided
        if account_id:
            logger.info("Using cross-account role for CloudWatch client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            cw_client = boto3_client('cloudwatch', region, assumed_credentials)
        else:
            logger.info("Using default credentials for CloudWatch client.")
            cw_client = boto3_client('cloudwatch', region)

        logger.debug('Calling describe_alarms with prefix {}'.format(AlarmNamePrefix))
        response = cw_client.describe_alarms(AlarmNamePrefix=AlarmNamePrefix)
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


def scan_and_process_alarm_tags(create_alarm_tag, default_alarms, metric_dimensions_map, sns_topic_arn, cw_namespace, create_default_alarms_flag, alarm_separator, alarm_identifier, region, account_id=None):
    """
    Scans EC2 instances and processes alarm tags. If an account ID is provided,
    assumes a cross-account role to access the EC2 client.
    """
    try:
        # Use cross-account role if account_id is provided
        if account_id:
            logger.info("Using cross-account role for EC2 client.")
            assumed_credentials = assume_cross_account_role(account_id, region)
            ec2_client = boto3_client('ec2', region, assumed_credentials)
        else:
            logger.info("Using default credentials for EC2 client.")
            ec2_client = boto3_client('ec2', region)

        # Separate wildcard alarms and default alarms
        default_filtered_alarms, wildcard_alarms = separate_wildcard_alarms(alarm_separator, cw_namespace,
                                                                            default_alarms)

        # Process instances
        for reservation in ec2_client.describe_instances()["Reservations"]:
            for instance in reservation["Instances"]:
                # Process only running instances
                if instance["State"]["Code"] > 16:
                    continue

                if check_alarm_tag(instance["InstanceId"], create_alarm_tag, region, account_id):
                    process_alarm_tags(instance["InstanceId"], instance, default_filtered_alarms, wildcard_alarms,
                                       metric_dimensions_map, sns_topic_arn, cw_namespace, create_default_alarms_flag,
                                       alarm_separator, alarm_identifier, region, account_id)

    except Exception as e:
        logger.error('Failure describing reservations: {}'.format(e))
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


def get_active_accounts_by_organizational_unit(ou_ids, management_account):
    region = "us-east-1"
    logger.info("Assuming role in organizations management account: {}".format(management_account))
    assumed_credentials = assume_management_account_role(management_account, region)
    client = boto3_client('organizations', region, assumed_credentials)
    accounts_by_ou = {}
    for ou_id in ou_ids:
        ou_id = ou_id.strip()
        paginator = client.get_paginator('list_accounts_for_parent')
        accounts = []
        for page in paginator.paginate(ParentId=ou_id):
            for account in page['Accounts']:
                if account['Status'] == 'ACTIVE':
                    accounts.append({
                        'AccountId': account['Id'],
                        'AccountName': account['Name'],
                        'Email': account['Email'],
                        'Status': account['Status']
                    })
        accounts_by_ou[ou_id] = accounts

    return accounts_by_ou
