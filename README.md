## Amazon CloudWatch Auto Alarms - Automatically create and configure CloudWatch alarms for EC2 instances
The CloudWatchEC2AutoAlarms AWS Lambda function enables you to quickly and automatically create and manage CloudWatch metric alarms for EC2 instances by tagging instances using the defined syntax.  
It prevents errors that may occur by manually creating alarms, reduces the time required to deploy alarms to a large number of instances, and reduces the skills gap required in order to create and manage alarms.  
It can be especially useful during a large migration to AWS where many instances may be migrated with a solution such as CloudEndure.

The AWS Lambda function creates the following alarms for Windows, Amazon Linux, Redhat, Ubuntu, or SUSE EC2 instances:
*  CPU Utilization
*  CPU Credit Balance (For T Class instances)
*  Disk Space
*  Memory

The CloudWatchEC2AutoAlarms Lambda function is configured to include alarms that align to [the basic metric set](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html)

Additional alarms can be automatically created by updating the **default_alarms** dictionary in [cw_ec2_auto_alarms.py](./cw_ec2_auto_alarms.py).

The created alarms can be configured to notify an SNS topic that you specify using the **DEFAULT_ALARM_SNS_TOPIC_ARN** environment variable.  See the **Setup** section for details.    

The metric alarms are created when an EC2 instance with the tag key **Create_Auto_Alarms** enters the **running** state and they are deleted when the instance is **terminated**.  
Alarms can be created when an instance is first launched or afterwards by stopping and starting the instance.

The metric alarms are created and configured based on EC2 tags which include the metric name, comparison, period, statistic, and threshold.

The tag name syntax for AWS provided metrics is:

AutoAlarm-<Namespace>-<MetricName>-<ComparisonOperator>-<Period>-<Statistic>

Where:

* Namespace is the CloudWatch Alarms namespace for the metric.  For AWS provided EC2 metrics, this is **EC2/AWS**.  For CloudWatch agent provided metrics, this is CWAgent by default.  
You can also specify a different name as described in the **Configuration** section.   
* MetricName is the name of the metric.  For example, CPUUtilization for EC2 total CPU utilization.
* ComparisonOperator is the comparison that should be used aligning to the ComparisonOperator parameter in the [PutMetricData](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricAlarm.html) Amazon CloudWatch API action.
* Period is the length of time used to evaluate the metric.  You can specify an integer value followed by s for seconds, m for minutes, h for hours, d for days, and w for weeks.  Your evaluation period should observe CloudWatch evaluation period limits.
* Statistic is the statistic for the MetricName specified, other than percentile.  

The tag value is used to specify the threshold.

For example, one of the preconfigured, default alarms that are included in the **default_alarms** dictionary is **AutoAlarm-AWS/EC2-CPUUtilization-GreaterThanThreshold-5m-Average**.
When an instance with the tag key **Create_Auto_Alarms** enters the **running** state, the instance will be tagged with this key and the default threshold value and then the associated alarm will be created.
Additional tags and alarms will also be created to the EC2 instance based on the platform. and alarms defined in the **default_alarms** dictionary.  Alarms will then be created based on these tag keys and values.  

Alarms can be updated by changing the tag key or value and stopping and starting the instance.

## Requirements
1.  The AWS CLI is required to deploy the Lambda function using the deployment instructions.
2.  The AWS CLI should be configured with valid credentials to create the CloudFormation stack, lambda function, and related resources.  You must also have rights to upload new objects to the S3 bucket you specify in the deployment steps.  
3.  EC2 instances must have the CloudWatch agent installed and configured with [the basic, standard, or advanced predefined metric sets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html) in order for the created alarms to work.  Scripts named [userdata_linux_basic.sh](./userdata_linux_basic.sh), [userdata_linux_standard.sh](./userdata_linux_standard.sh), and [userdata_linux_advanced.sh](./userdata_linux_advanced.sh) are provided to install and configure the CloudWatch agent on Linux based EC2 instances with the predefined metric sets.  The lambda function is implemented to support the basic metric set.
   
## Setup
There are a number of settings that can be customized by updating the CloudWatchEC2AutoAlarms Lambda function environment variables defined in the [sam.yaml](./sam.yaml) CloudFormation template.
The settings will only affect new alarms that you create so you should customize these values to meet your requirements before you deploy the Lambda function.
The following list provides a description of the setting along with the environment variable name and default value:

* Alarm Tag:  The CloudWatchEC2AutoAlarms Lambda function will only create alarms for instances that are tagged with this specified name tag.  If you want to use a different name, enter it here:
    * ALARM_TAG: Create_Auto_Alarms
* CloudWatch Namespace:  You can change the namespace where the Lambda function should look for your CloudWatch metrics.  The default CloudWatch agent metrics namespace is CWAgent.  
If your CloudWatch agent configuration is using a different namespace that update it here:
    * CLOUDWATCH_NAMESPACE: CWAgent
 
* Alarm Thresholds:  You can update the default thresholds used to create new CloudWatch Metric alarms by updating the following environment variables:
    * ALARM_CPU_HIGH_THRESHOLD: 75
    * ALARM_CPU_CREDIT_BALANCE_LOW_THRESHOLD: 100
    * ALARM_MEMORY_HIGH_THRESHOLD: 75
    * ALARM_DISK_PERCENT_LOW_THRESHOLD: 20

* Notifications:  You can define an SNS topic that the CloudWatchEC2AutoAlarms Lambda function will specify as the notification target for created alarms.  
This environment variable is commented out by default, so no notifications are sent unless you uncomment this variable and set it to an appropriate SNS ARN before deployment:
    * DEFAULT_ALARM_SNS_TOPIC_ARN: <no default value>


## Deploy 

To deploy this lambda function, clone this repository.  Then run the following command with **<s3_bucket_name>** updated to reflect the S3 bucket that you want to use to deploy the Lambda function.  The S3 bucket should be in the same region that you want to deploy the lambda function.  Ensure that your [AWS credentials are set as environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html):

    aws cloudformation package --template-file sam.yaml --s3-bucket <s3_bucket_name> --output-template-file sam-deploy.yaml

After the Lambda function has been packaged and the sam-deploy.yaml file has been created, run the following command with **<region_name>** updated to reflect the region you wish to deploy the Lambda function:

    aws cloudformation deploy --template-file sam-deploy.yaml --stack-name cloudwatch-ec2-auto-alarms --capabilities CAPABILITY_IAM --region <region>

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
