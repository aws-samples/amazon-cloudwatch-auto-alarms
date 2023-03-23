# CloudWatchAutoAlarms - Automatically create a set of CloudWatch alarms with tagging

![CloudWatchAutoAlarms Architecture Diagram](./CloudWatchAutoAlarmsArchitecture.png)

The CloudWatchAutoAlarms AWS Lambda function enables you to quickly and automatically create a standard set of CloudWatch alarms for your Amazon EC2 instances or AWS Lambda functions using tags.  It prevents errors that may occur by manually creating alarms, reduces the time required to deploy alarms, and reduces the skills gap required in order to create and manage alarms.  It can be especially useful during a large migration to AWS where many resources may be migrated into your AWS account at once.

The default configuration creates alarms for the following Amazon EC2 metrics for Windows, Amazon Linux, Redhat, Ubuntu, or SUSE EC2 instances:
*  CPU Utilization
*  CPU Credit Balance (For T Class instances)
*  Disk Space Used % (Amazon CloudWatch agent [predefined basic metric](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html))
*  Memory Used % (Amazon CloudWatch agent [predefined basic metric](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html))

The default configuration also creates alarms for the following [AWS Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html#monitoring-metrics-types):

* Errors
* Throttles

You can change or add alarms by updating the **default_alarms** dictionary in [cw_auto_alarms.py](src/cw_auto_alarms.py).

The created alarms can be configured to notify an Amazon SNS topic that you specify using the **DEFAULT_ALARM_SNS_TOPIC_ARN** environment variable.  See the **Setup** section for details.

The Amazon CloudWatch alarms are created when an EC2 instance with the tag key **Create_Auto_Alarms** enters the **running** state and they are deleted when the instance is **terminated**.
Alarms can be created when an instance is first launched or afterwards by stopping and starting the instance.

The alarms are created and configured based on EC2 tags which include the metric name, comparison, period, statistic, and threshold.

The tag name syntax for AWS provided metrics is:

AutoAlarm-\<**Namespace**>-\<**MetricName**>-\<**ComparisonOperator**>-\<**Period**>-\<**EvaluationPeriods**>-\<**Statistic**>-\<**Description**>

Where:

* **Namespace** is the CloudWatch Alarms namespace for the metric.  For AWS provided EC2 metrics, this is **AWS/EC2**.  For CloudWatch agent provided metrics, this is CWAgent by default.
    You can also specify a different name as described in the **Configuration** section.
* **MetricName** is the name of the metric.  For example, CPUUtilization for EC2 total CPU utilization.
* **ComparisonOperator** is the comparison that should be used aligning to the ComparisonOperator parameter in the [PutMetricData](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricAlarm.html) Amazon CloudWatch API action.
* **Period** is the length of time used to evaluate the metric.  You can specify an integer value followed by s for seconds, m for minutes, h for hours, d for days, and w for weeks.  Your evaluation period should observe CloudWatch evaluation period limits.
* **EvaluationPeriods** is the number of periods on which to evaluate the alarm.  This property is optional and if it is left out, defaults to 1.
* **Statistic** is the statistic for the MetricName specified, other than percentile.
* **Description** is the description for the CloudWatch Alarm.  This property is optional, and if it is left out then a default description is used.

The tag value is used to specify the threshold.  You can also [create alarms for custom Amazon CloudWatch metrics](#alarming-on-custom-amazon-ec2-metrics).

For example, one of the preconfigured, default alarms that are included in the **default_alarms** dictionary is **AutoAlarm-AWS/EC2-CPUUtilization-GreaterThanThreshold-5m-1-Average-Created_by_CloudWatchAutoAlarms**.
When an instance with the tag key **Create_Auto_Alarms** enters the **running** state, an alarm for the AWS provided **CPUUtilization** CloudWatch EC2 metric will be created.
Additional alarms will also be created for the EC2 instance based on the platform and alarms defined in the **default_alarms** python dictionary defined in [cw_auto_alarms.py](src/cw_auto_alarms.py).

Alarms can be updated by changing the tag key or value and stopping and starting the instance.

## Requirements

1. The AWS CLI is required to deploy the Lambda function using the deployment instructions.
2. The AWS CLI should be configured with valid credentials to create the CloudFormation stack, lambda function, and related resources.  You must also have rights to upload new objects to the S3 bucket you specify in the deployment steps.
3. EC2 instances must have the CloudWatch agent installed and configured with [the basic, standard, or advanced predefined metric sets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html) in order for the default alarms for custom CloudWatch metrics to work.  Scripts named [userdata_linux_basic.sh](./userdata_linux_basic.sh), [userdata_linux_standard.sh](./userdata_linux_standard.sh), and [userdata_linux_advanced.sh](./userdata_linux_advanced.sh) are provided to install and configure the CloudWatch agent on Linux based EC2 instances with their respective predefined metric sets.

## Setup

There are a number of settings that can be customized by updating the CloudWatchAutoAlarms Lambda function environment variables defined in the [CloudWatchAutoAlarms.yaml](./CloudWatchAutoAlarms.yaml) CloudFormation template.
The settings will only affect new alarms that you create so you should customize these values to meet your requirements before you deploy the Lambda function.
The following list provides a description of the setting along with the environment variable name and default value:

* **ALARM_TAG**: Create_Auto_Alarms
    * The CloudWatchAutoAlarms Lambda function will only create alarms for instances that are tagged with this name tag.  The default tag name is Create_Auto_Alarms.  If you want to use a different name, change the value of the ALARM_TAG environment variable.
* **CREATE_DEFAULT_ALARMS**: true
    * When true, this will result in the default alarm set being created when the **Create_Auto_Alarms** tag is present.  If set to false, then alarms will be created only for the alarm tags  defined on the instance.
* **CLOUDWATCH_NAMESPACE**: CWAgent
    * You can change the namespace where the Lambda function should look for your CloudWatch metrics. The default CloudWatch agent metrics namespace is CWAgent.  If your CloudWatch agent configuration is using a different namespace, then update the  CLOUDWATCH_NAMESPACE environment variable.
* **CLOUDWATCH_APPEND_DIMENSIONS**: InstanceId, ImageId, InstanceType, AutoScalingGroupName
    * You can add EC2 metric dimensions to all metrics collected by the CloudWatch agent.  This environment variable aligns to your CloudWatch configuration setting for [**append_dimensions**](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Configuration-File-Details.html#CloudWatch-Agent-Configuration-File-Metricssection).  The default setting includes all the supported dimensions:  InstanceId, ImageId, InstanceType, AutoScalingGroupName
* **DEFAULT_ALARM_SNS_TOPIC_ARN**:  arn:${AWS::Partition}:sns:${AWS::Region}:${AWS::AccountId}:CloudWatchAutoAlarmsSNSTopic
    * You can define an Amazon Simple Notification Service (Amazon SNS) topic that the Lambda function will specify as the notification target for created alarms. You provide the Amazon SNS Topic Amazon Resource Name (ARN) with the **AlarmNotificationARN** parameter when you deploy the CloudWatchAutoAlarms.yaml CloudFormation template.  If you leave the **AlarmNotificationARN** parameter value blank, then this environment variable is not set and created alarms won't use notifications.
* **ALARM_IDENTIFIER_PREFIX**:  AutoAlarm
    * The prefix name that is added to the beginning of each CloudWatch alarm created by the solution.  (e.g. For "AutoAlarm":  (e.g. AutoAlarm-i-00e4f327736cb077f-CPUUtilization-GreaterThanThreshold-80-5m))  You should update this variable via the **AlarmIdentifierPrefix** in the [CloudWatchAutoAlarms.yaml](./CloudWatchAutoAlarms.yaml) CloudFormation template so that the IAM policy is updated to align with your custom name.

You can update the thresholds for the default alarms by updating the following environment variables:


   **For Amazon EC2**:
    * **ALARM_CPU_HIGH_THRESHOLD**: 75
    * **ALARM_CPU_CREDIT_BALANCE_LOW_THRESHOLD**: 100
    * **ALARM_MEMORY_HIGH_THRESHOLD**: 75
    * **ALARM_DISK_PERCENT_LOW_THRESHOLD**: 20

   **For AWS Lambda**:
    * **ALARM_LAMBDA_ERROR_THRESHOLD**: 0
    * **ALARM_LAMBDA_THROTTLE_THRESHOLD**: 0

## Deploy

1. Clone the amazon-cloudwatch-auto-alarms github repository to your computer using the following command:

       git clone https://github.com/aws-samples/amazon-cloudwatch-auto-alarms
2. Configure the AWS CLI with credentials for your AWS account.  This walkthrough uses temporary credentials provided by AWS Single Sign On using the **Command line or programmatic access** option.  This sets the **AWS_ACCESS_KEY_ID**, **AWS_SECRET_ACCESS_KEY**, and **AWS_SESSION_TOKEN** AWS environment variables with the appropriate credentials for use with the AWS CLI.
3. Create an Amazon SNS topic that CloudWatchAutoAlarms will use for notifications. You can use this sample Amazon SNS CloudFormation template to create an SNS topic.  Leave the OrganizationID parameter blank, it is used for multi-account deployments.

       aws cloudformation create-stack --stack-name amazon-cloudwatch-auto-alarms-sns-topic \
       --template-body file://CloudWatchAutoAlarms-SNS.yaml \
       --parameters ParameterKey=OrganizationID,ParameterValue="" \
       --region <enter your aws region id, e.g. "us-east-1">
4. Create an S3 bucket that will be used to store and access the CloudWatchAutoAlarms lambda function deployment package if you don't have one.  You can use [this sample S3 CloudFormation template](./CloudWatchAutoAlarms-S3.yaml).  You can leave the AWS Organizations ID parameter blank if this lambda function will only be deployed in your current account:

       aws cloudformation create-stack --stack-name amazon-cloudwatch-auto-alarms-s3-bucket \
        --template-body file://CloudWatchAutoAlarms-S3.yaml \
        --parameters ParameterKey=OrganizationID,ParameterValue="" \
        --region <enter your aws region id, e.g. "us-east-1">
5. Update the environment variables in the [CloudWatchAutoAlarms CloudFormation template](./CloudWatchAutoAlarms.yaml) to configure default settings such as alarm thresholds.
6. Create a zip file containing the CloudWatchAutoAlarms AWS Lambda function code located in the [src](./src) directory.  This is the deployment package that you will use to deploy the AWS Lambda function.  On a Mac, you can use the zip command:

       zip -j amazon-cloudwatch-auto-alarms.zip src/*
7. Copy the **amazon-cloudwatch-auto-alarms.zip** file to your S3 bucket.

       aws s3 cp amazon-cloudwatch-auto-alarms.zip s3://<bucket name>

   If you created an S3 bucket using [this sample S3 CloudFormation template](./CloudWatchAutoAlarms-S3.yaml) in step 3, then you can get the bucket name from the AWS Management console or run the following AWS CLI command:

       aws cloudformation describe-stacks --stack-name amazon-cloudwatch-auto-alarms-s3-bucket \
       --query "Stacks[0].Outputs[?ExportName=='amazon-cloudwatch-auto-alarms-bucket-name'].OutputValue" \
       --output text \
       --region <enter your aws region id, e.g. "us-east-1">

8. Deploy the AWS lambda function using the deployment package you uploaded to your S3 bucket:

       aws cloudformation create-stack --stack-name amazon-cloudwatch-auto-alarms \
       --template-body file://CloudWatchAutoAlarms.yaml \
       --capabilities CAPABILITY_IAM \
       --parameters ParameterKey=S3DeploymentKey,ParameterValue=amazon-cloudwatch-auto-alarms.zip \
       ParameterKey=S3DeploymentBucket,ParameterValue=<S3 bucket with your deployment package> \
       ParameterKey=AlarmNotificationARN,ParameterValue=<SNS Topic ARN for Alarm Notifications> \
       --region <enter your aws region id, e.g. "us-east-1">

   If you don't want to enable SNS notifications, you can set the **ParameterValue** to **""** for **AlarmNotificationARN**.

   You can retrieve the SNS Topic ARN from step #3 for the **AlarmNotificationARN** parameter value by running the following command:

       aws cloudformation describe-stacks --stack-name amazon-cloudwatch-auto-alarms-sns-topic \
       --query "Stacks[0].Outputs[?ExportName=='amazon-cloudwatch-auto-alarms-sns-topic-arn'].OutputValue" \
       --output text --region <enter your aws region id, e.g. "us-east-1">

## Activate

In order to create the default alarm set for an Amazon EC2 instance or AWS Lambda function, you simply need to tag the Amazon EC2 instance or AWS Lambda function with the activation tag key defined by the **ALARM_TAG** environment variable.  The default tag activation key is **Create_Auto_Alarms**.

For Amazon EC2 instances, you must add this tag during instance launch or you can add this tag at any time to an instance and then stop and start the instance in order to create the default alarm set as well as any custom, instance specific alarms.

You can also manually invoke the CloudWatchAutoAlarms lambda function with the following event payload to create / update EC2 alarms without having to stop and start your EC2 instances:

```json
{
  "action": "scan"
}
```
You can do this with a test execution of the CloudWatchAUtoAlarms AWS Lambda function.  Open the  AWS Lambda Management Console and perform a test invocation from the **Test** tab with the payload provided here.

For AWS Lambda, you can add this tag to an AWS Lambda function at any time in order to create the default alarm set as well as any custom, function specific alarms.


## Changing the default alarm set

You can add, remove, and customize alarms in the default alarm set.  The default alarms are defined in the **default_alarms** python dictionary in [cw_auto_alarms.py](src/cw_auto_alarms.py).

In order to create an alarm, you must uniquely identify the metric that you want to alarm on.  Standard Amazon EC2 metrics include the **InstanceId** dimension to uniquely identify each standard metric associated with an EC2 instance.  If you want to add an alarm based upon a standard EC2 instance metric, then you can use the tag name syntax:
AutoAlarm-AWS/EC2-\<**MetricName**>-\<**ComparisonOperator**>-\<**Period**>-\<**EvaluationPeriods**>-\<**Statistic**>-\<**Description**>
This syntax doesn't include any dimension names because the InstanceId dimension is used for metrics in the **AWS/EC2** namespace.  These AWS provided EC2 metrics are common across all platforms for EC2.

Similarly, AWS Lambda metrics include the **FunctionName** dimension to uniquely identify each standard metric associated with an AWS Lambda function.  If you want to add an alarm based upon a standard AWS Lambda metric, then you can use the tag name syntax:
AutoAlarm-AWS/Lambda-\<**MetricName**>-\<**ComparisonOperator**>-\<**Period**>-\<**EvaluationPeriods**>-\<**Statistic**>-\<**Description**>
You can add any standard Amazon CloudWatch metric for Amazon EC2 or AWS Lambda into the **default_alarms** dictionary under the **AWS/EC2** or **AWS/Lambda** dictionary key using this tag syntax.

## Alarming on custom Amazon EC2 metrics

Metrics captured by the Amazon CloudWatch agent are considered custom metrics.  These metrics are created in the **CWAgent** namespace by default.  Custom metrics may have any number of dimensions in order to uniquely identify a metric.  Additionally, the metric dimensions may be named differently based upon the underlying platform for the EC2 instance.

For example, the metric name used to measure the disk space utilization is named **disk_used_percent** in Linux and **LogicalDisk % Free Space** in Windows.  The dimensions are also different, in Linux you must also include the **device**, **fstype**, and **path** dimensions in order to uniquely identify a disk.  In Windows, you must include the **objectname** and **instance** dimensions.

Consequently, it is more difficult to automatically create alarms across different platforms for custom CloudWatch EC2 instance metrics.

The **disk_used_percent** metric for Linux has the additional dimensions:  **\'device', 'fstype', 'path'**.  For metrics with custom dimensions, you can include the dimension name and value in the tag key syntax:
AutoAlarm-\<**Namespace**>-\<**MetricName**>-\<**DimensionName-DimensionValue...**>-\<**ComparisonOperator**>-\<**Period**>-\<**EvaluationPeriods**>-\<**Statistic**>-\<**Description**>
For example, the tag name used to create an alarm for the average **disk_used_percent** over a 5 minute period for the root partition on an Amazon Linux instance in the **CWAgent** namespace is:
**AutoAlarm-CWAgent-disk_used_percent-device-xvda1-fstype-xfs-path-/-GreaterThanThreshold-5m-1-Average-exampleDescription**
Where the **device** dimension has a value of **xvda1**, the **fstype** dimension has a value of **xfs**, and the **path** dimension has a value of **/**.

This syntax and approach allows you to collectively support metrics with different numbers of dimensions and names.  Using this syntax, you can add alarms for metrics with custom dimensions to the appropriate platform in the **default_alarms** dictionary in [cw_auto_alarms.py](src/cw_auto_alarms.py)

You should also make sure that the **CLOUDWATCH_APPEND_DIMENSIONS** environment variable is set correctly in order to ensure that created alarms include these dimensions.  The lambda function will dynamically lookup the values for these dimensions at runtime.

If your dimensions name uses the default separator character '-', then you can update the **alarm_separator** variable in [cw_auto_alarms.py](src/cw_auto_alarms.py) with an alternative seperator character such as '~'.
## Create a specific alarm for a specific EC2 instance using tags

You can create alarms that are specific to an individual EC2 instance by adding a tag to the instance using the tag key syntax described in [changing the default alarm set](#changing-the-default-alarm-set).  Simply add a tag to the instance on launch or restart the instance after you have added the tag.  You can also update the thresholds for created alarms by updating the tag values, causing the alarm to be updated when the instance is stopped and started.

For example, to add an alarm for the Amazon EC2 **StatusCheckFailed** CloudWatch metric for an existing EC2 instance:
1. On the **Tags** tab, choose **Manage tags**, and then choose **Add tag**. For **Key**, enter **AutoAlarm-AWS/EC2-StatusCheckFailed-GreaterThanThreshold-5m-1-Average-exampleDescription**. For Value, enter **1**. Choose **Save**.
2. Stop and start the Amazon EC2 instance.
3. After the instance is stopped and restarted, go to the **Alarms** page in the CloudWatch console to confirm that the alarm was created.  You should find a new alarm named **AutoAlarm-<instance id omitted>-StatusCheckFailed-GreaterThanThreshold-1-5m-1p-exampleDescription**.

## Creating a specific alarm for a specific AWS Lambda function using tags

You can create alarms that are specific to an individual AWS Lambda function by adding a tag to the instance using the tag key syntax described in [changing the default alarm set](#changing-the-default-alarm-set).

## Deploying in a multi-region, multi-account environment

You can deploy the CloudWatchAutoAlarms lambda function into a multi-account, multi-region environment by using [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html).

Follow [steps 1 through 7 in the normal deployment process](#deploy).   For step #3 and step #4, enter your AWS Organizations ID for the **OrganizationID** parameter in the [sample S3 CloudFormation template](./CloudWatchAutoAlarms-S3.yaml) and [sample SNS CloudFormation template](./CloudWatchAutoAlarms-SNS.yaml).  This will update the resource policy to allow access to all accounts in your AWS organization.

Continue with the following steps to deploy a service managed AWS StackSet for the CloudWatchAutoAlarms lambda function.  This will deploy the CloudWatchAutoAlarms Lambda function into the organization units that you specify.  The lambda function will also be automatically deployed to new accounts in the AWS organization.

1. Use the [CloudWatchAutoAlarms CloudFormation template](./CloudWatchAutoAlarms.yaml) to deploy the Lambda function across multiple regions and accounts in your AWS Organization.  This walkthrough deploys a service managed CloudFormation StackSet in the AWS Organizations master account.  You must also specify the account ID where the S3 deployment bucket was created so the same S3 bucket is used across account deployments in your organization.  Use the following command to deploy the service managed CloudFormation StackSet:

       aws cloudformation create-stack-set --stack-set-name amazon-cloudwatch-auto-alarms \
       --template-body file://CloudWatchAutoAlarms.yaml \
       --capabilities CAPABILITY_NAMED_IAM \
       --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false \
       --permission-model SERVICE_MANAGED \
       --parameters ParameterKey=S3DeploymentKey,ParameterValue=amazon-cloudwatch-auto-alarms.zip \
       ParameterKey=S3DeploymentBucket,ParameterValue=<S3 bucket with your deployment package> \
       --region <enter your aws region id, e.g. "us-east-1">

      2. After the StackSet is created, you can specify which AWS accounts and regions the StackSet should be deployed.  For service managed StackSets, you specify your AWS Organization ID or AWS Organizational Unit IDs to deploy the lambda function to all current and future accounts within them.   Use the following AWS CLI command to deploy the StackSet to your organization / organizational units:

       aws cloudformation create-stack-instances --stack-set-name amazon-cloudwatch-auto-alarms \
       --operation-id amazon-cloudwatch-auto-alarms-deployment-$(date | md5) \
       --deployment-targets OrganizationalUnitIds=<Enter the target OUs where the lambda function should be deployed> \
       --regions <enter the target regions where the lambda function should be deployed e.g. "us-east-1"> \
       --region <enter your aws region id, e.g. "us-east-1">

   You can monitor the progress and status of the StackSet operation in the AWS CloudFormation service console.

   Once the deployment is complete, the status will change from **RUNNING** to **SUCCEEDED**.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
