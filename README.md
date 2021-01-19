## CloudWatchAutoAlarms - Automatically create and configure CloudWatch alarms for EC2 instances

![CloudWatchAutoAlarms Architecture Diagram](./CloudWatchAutoAlarmsArchitecture.png)

The CloudWatchAutoAlarms AWS Lambda function enables you to quickly and automatically create and manage CloudWatch metric alarms for EC2 instances by tagging instances using the defined syntax.  It prevents errors that may occur by manually creating alarms, reduces the time required to deploy alarms to a large number of instances, and reduces the skills gap required in order to create and manage alarms.  It can be especially useful during a large migration to AWS where many instances may be migrated with a solution such as CloudEndure.

The AWS Lambda function creates the following alarms for Windows, Amazon Linux, Redhat, Ubuntu, or SUSE EC2 instances:
*  CPU Utilization
*  CPU Credit Balance (For T Class instances)
*  Disk Space
*  Memory

The CloudWatchAutoAlarms Lambda function is configured to include alarms that align to [the basic metric set](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html)

Additional alarms can be automatically created by updating the **default_alarms** dictionary in [cw_auto_alarms.py](./cw_auto_alarms.py).

The created alarms can be configured to notify an SNS topic that you specify using the **DEFAULT_ALARM_SNS_TOPIC_ARN** environment variable.  See the **Setup** section for details.    

The metric alarms are created when an EC2 instance with the tag key **Create_Auto_Alarms** enters the **running** state and they are deleted when the instance is **terminated**.  
Alarms can be created when an instance is first launched or afterwards by stopping and starting the instance.

The metric alarms are created and configured based on EC2 tags which include the metric name, comparison, period, statistic, and threshold.

The tag name syntax for AWS provided metrics is:

AutoAlarm-\<**Namespace**>-\<**MetricName**>-\<**ComparisonOperator**>-\<**Period**>-\<**Statistic**>

Where:

* **Namespace** is the CloudWatch Alarms namespace for the metric.  For AWS provided EC2 metrics, this is **AWS/EC2**.  For CloudWatch agent provided metrics, this is CWAgent by default.  
You can also specify a different name as described in the **Configuration** section.   
* **MetricName** is the name of the metric.  For example, CPUUtilization for EC2 total CPU utilization.
* **ComparisonOperator** is the comparison that should be used aligning to the ComparisonOperator parameter in the [PutMetricData](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricAlarm.html) Amazon CloudWatch API action.
* **Period** is the length of time used to evaluate the metric.  You can specify an integer value followed by s for seconds, m for minutes, h for hours, d for days, and w for weeks.  Your evaluation period should observe CloudWatch evaluation period limits.
* **Statistic** is the statistic for the MetricName specified, other than percentile.  

The tag value is used to specify the threshold.

For example, one of the preconfigured, default alarms that are included in the **default_alarms** dictionary is **AutoAlarm-AWS/EC2-CPUUtilization-GreaterThanThreshold-5m-Average**.
When an instance with the tag key **Create_Auto_Alarms** enters the **running** state, an alarm for the AWS provided **CPUUtilization** CloudWatch EC2 metric will be created.
Additional tags and alarms will also be created for the EC2 instance based on the platform and alarms defined in the **default_alarms** python dictionary defined in [cw_auto_alarms.py](./cw_auto_alarms.py).  

Alarms can be updated by changing the tag key or value and stopping and starting the instance.

### Adding / customizing the default alarms created
You can add or remove the alarms that are created by default.  The default alarms are defined in the **default_alarms** python dictionary in [cw_auto_alarms.py](./cw_auto_alarms.py).  The default configuration uses standard Amazon EC2 instance metrics.  

In order to create an alarm, you must uniquely identify the metric that you want to alarm on.  Standard Amazon EC2 metrics include the **InstanceId** dimension to uniquely identify each standard metric associated with an EC2 instance.  If you want to add an alarm based upon a standard EC2 instance metric, then you can use the tag name syntax:

AutoAlarm-AWS/EC2-\<**MetricName**>-\<**ComparisonOperator**>-\<**Period**>-\<**Statistic**>

This syntax doesn't include any dimension names because the InstanceId dimension is used for metrics in the **AWS/EC2** namespace.  These metrics are also standardized across all supported platforrms for EC2.  You can add any standard Amazon EC2 CloudWatch metric into the **default_alarms** dictionary under the **All** dictionary key using this tag syntax.

#### Alarming on custom Amazon EC2 metrics
Metrics captured by the Amazon CloudWatch agent are considered custom metrics.  These metrics are created in the **CWAgent** namespace by default.  Custom metrics may use any number of dimensions in order to uniquely identify a metric.  Additionally, the metric dimensions may be named differently based upon the underlying platform for the EC2 instance.

For example, the metric name used to measure the disk space utilization is named **disk_used_percent** in Linux and **LogicalDisk % Free Space** in Windows.  The dimensions are also different, in Linux you must also include the **device**, **fstype**, and **path** dimensions in order to uniquely identify a disk.  In Windows, you must include the **objectname** and **instance** dimensions.

Consequently, it is more difficult to automatically create alarms across different platforms for custom CloudWatch EC2 instance metrics.  This solution includes a python dictionary named **metric_dimensions_map** that identifies the required dimensions for a custom CloudWatch EC2 instance metric.  The dimensions listed in this map correlate directly to the tag name syntax for that metric.

For example, the **disk_used_percent** key has the value:  **\['device', 'fstype', 'path']**.  The tag name syntax then includes the values for each dimension in the tag name:

AutoAlarm-\<**Namespace**>-\<**MetricName**>-\<**DimensionValues...**>-\<**ComparisonOperator**>-\<**Period**>-\<**Statistic**> 

For example, the tag name used to create an alarm for the average **disk_used_percent** over a 5 minute period for the root partition on an Amazon Linux instance in the **CWAgent** namespace is:

**AutoAlarm-CWAgent-disk_used_percent-xvda1-xfs-/-GreaterThanThreshold-5m-Average**

where **xvda1** is the value for the **device** dimension, **xfs** is the value for the **fstype** dimension, and **/** is the value for the **path** dimension.
 
This syntax and approach allows you to collectively support metrics with different numbers of dimensions and names.  In order to include a custom alarm in your default alarms, update the **metric_dimensions_map** to reflect the dimensions of the metric and then add the metric to the appropriate platform to the **default_alarms** dictionary in [cw_auto_alarms.py](./cw_auto_alarms.py)

You should also make sure that the **CLOUDWATCH_APPEND_DIMENSIONS** environment variable is set correctly in order to ensure that dynamically added dimensions are accounted for by the solution.  The lambda function will dynamically lookup the values for these dimensions at runtime.

## Requirements
1.  The AWS CLI is required to deploy the Lambda function using the deployment instructions.
2.  The AWS CLI should be configured with valid credentials to create the CloudFormation stack, lambda function, and related resources.  You must also have rights to upload new objects to the S3 bucket you specify in the deployment steps.  
3.  EC2 instances must have the CloudWatch agent installed and configured with [the basic, standard, or advanced predefined metric sets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-wizard.html) in order for the created alarms to work.  Scripts named [userdata_linux_basic.sh](./userdata_linux_basic.sh), [userdata_linux_standard.sh](./userdata_linux_standard.sh), and [userdata_linux_advanced.sh](./userdata_linux_advanced.sh) are provided to install and configure the CloudWatch agent on Linux based EC2 instances with the predefined metric sets.  The lambda function is implemented to support the basic metric set by default.
   
## Setup
There are a number of settings that can be customized by updating the CloudWatchAutoAlarms Lambda function environment variables defined in the [sam.yaml](./sam.yaml) CloudFormation template.
The settings will only affect new alarms that you create so you should customize these values to meet your requirements before you deploy the Lambda function.
The following list provides a description of the setting along with the environment variable name and default value:

* **ALARM_TAG**: Create_Auto_Alarms
    * The CloudWatchAutoAlarms Lambda function will only create alarms for instances that are tagged with this name tag.  The default tag name is Create_Auto_Alarms.  If you want to use a different name, change the value of the ALARM_TAG environment variable.
* **CLOUDWATCH_NAMESPACE**: CWAgent
    * You can change the namespace where the Lambda function should look for your CloudWatch metrics. The default CloudWatch agent metrics namespace is CWAgent.  If your CloudWatch agent configuration is using a different namespace, then update the  CLOUDWATCH_NAMESPACE environment variable.
* **CLOUDWATCH_APPEND_DIMENSIONS**: InstanceId, ImageId, InstanceType, AutoScalingGroupName 
    * You can add EC2 metric dimensions to all metrics collected by the CloudWatch agent.  This environment variable aligns to your CloudWatch configuration setting for append_dimensions.  The default setting includes all the supported dimensions:  InstanceId, ImageId, InstanceType, AutoScalingGroupName
* **DEFAULT_ALARM_SNS_TOPIC_ARN**:  arn:aws:sns:${AWS::Region}:${AWS::AccountId}:CloudWatchAutoAlarmsSNSTopic
    * You can define an Amazon Simple Notification Service (Amazon SNS) topic that the Lambda function will specify as the notification target for created alarms. This environment variable is commented out by default, so notifications are not sent unless you uncomment this variable and set it to an appropriate Amazon SNS ARN before deployment.  You can use this sample Amazon SNS topic CloudFormation template for the walkthrough.
* You can update the thresholds for the default alarms by updating the following environment variables:
    * ALARM_CPU_HIGH_THRESHOLD: 75
    * ALARM_CPU_CREDIT_BALANCE_LOW_THRESHOLD: 100
    * ALARM_MEMORY_HIGH_THRESHOLD: 75
    * ALARM_DISK_PERCENT_LOW_THRESHOLD: 20

* Alarm Tag:  The CloudWatchAutoAlarms Lambda function will only create alarms for instances that are tagged with this specified name tag.  If you want to use a different name, enter it here:
    * ALARM_TAG: Create_Auto_Alarms

* CloudWatch Namespace:  You can change the namespace where the Lambda function should look for your CloudWatch metrics.  The default CloudWatch agent metrics namespace is CWAgent.  
If your CloudWatch agent configuration is using a different namespace that update it here:
    * CLOUDWATCH_NAMESPACE: CWAgent

* Additional Dimensions:   
* Alarm Thresholds:  You can update the default thresholds used to create new CloudWatch Metric alarms by updating the following environment variables:
    * ALARM_CPU_HIGH_THRESHOLD: 75
    * ALARM_CPU_CREDIT_BALANCE_LOW_THRESHOLD: 100
    * ALARM_MEMORY_HIGH_THRESHOLD: 75
    * ALARM_DISK_PERCENT_LOW_THRESHOLD: 20

* Notifications:  You can define an SNS topic that the CloudWatchAutoAlarms Lambda function will specify as the notification target for created alarms.  
This environment variable is commented out by default, so no notifications are sent unless you uncomment this variable and set it to an appropriate SNS ARN before deployment:
    * DEFAULT_ALARM_SNS_TOPIC_ARN: <no default value>


## Deploy 

To deploy this lambda function, clone this repository.  Then run the following command with **<s3_bucket_name>** updated to reflect the S3 bucket that you want to use to deploy the Lambda function.  The S3 bucket should be in the same region that you want to deploy the lambda function.  Ensure that your [AWS credentials are set as environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html):

    aws cloudformation package --template-file sam.yaml --s3-bucket <s3_bucket_name> --output-template-file sam-deploy.yaml

After the Lambda function has been packaged and the sam-deploy.yaml file has been created, run the following command with **<region_name>** updated to reflect the region you wish to deploy the Lambda function:

    aws cloudformation deploy --template-file sam-deploy.yaml --stack-name cloudwatch-ec2-auto-alarms --capabilities CAPABILITY_IAM --region <region>

## Deploying in a multi-region, multi-account environment

You can deploy the CloudWatchAutoAlarms lambda function into a multi-account, multi-region environment by using [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html).  In order to deploy an AWS Lambda function with StackSets you must first copy the CloudFormation template to an S3 bucket that is accessible by all your accounts and regions.  One way to accomplish this is by creating an S3 bucket that grants permissions to all the accounts in your AWS organization.  You can use [this sample Amazon S3 CloudFormation template](https://github.com/aws-samples/amazon-cloudwatch-auto-alarms/blob/main/CloudWatchAutoAlarms-S3.yaml) to create an S3 bucket called **amazon-cloudwatch-auto-alarms-bucket-<Your Account ID>**.  The CloudFormation template includes an S3 bucket policy that grants read permissions to an AWS Organizations ID that you specify via a template parameter.  If you leave the template parameter blank, then the policy statements that grant organization access are not included.  If you are using a single account, leave the AWS Organizations ID parameter blank.  This will still allow you to deploy the lambda function using the created S3 bucket across multiple regions in a single account.  

Follow these steps to deploy the CloudWatchAutoAlarms lambda function across multiple regions and accounts within your AWS Organization:
1.	Clone the amazon-cloudwatch-auto-alarms github repository to your computer using the following command:

    git clone https://github.com/aws-samples/amazon-cloudwatch-auto-alarms

2.	Configure the AWS CLI with credentials for your AWS account.  This walkthrough uses temporary credentials provided by AWS Single Sign On using the **Command line or programmatic access** option.  This sets the **AWS_ACCESS_KEY_ID**, **AWS_SECRET_ACCESS_KEY**, and **AWS_SESSION_TOKEN** AWS environment variables with the appropriate credentials for use with the AWS CLI.
3.	Create an S3 bucket that will be used to store and access the CloudWatchAutoAlarms lambda function deployment package from multiple regions and accounts.  You can use [this sample S3 CloudFormation template](https://github.com/aws-samples/amazon-cloudwatch-auto-alarms/blob/main/CloudWatchAutoAlarms-S3.yaml) which also configures a bucket policy to provide read access to your AWS Organization.  You can deploy this using the AWS CLI with the following command (Note:  The Organization ID is omitted in this example):

    aws cloudformation create-stack --stack-name amazon-cloudwatch-auto-alarms-s3-bucket --parameters ParameterKey=OrganizationID,ParameterValue=<org id> --template-body file://CloudWatchAutoAlarms-S3.yaml —region us-east-1

4.	Update the environment variables in the CloudWatchAutoAlarms CloudFormation template to configure default settings such as alarm thresholds.  Note that this template references the S3 bucket that you created earlier in this walkthrough.  Also note that this template references a zip file named amazon-cloudwatch-auto-alarms.zip.  
5.	Create the **amazon-cloudwatch-auto-alarms.zip** zip file for the CloudWatchAutoAlarms lambda deployment package.  On mac, you can use the zip command:

    zip amazon-cloudwatch-auto-alarms.zip *.py

6.	Copy the **amazon-cloudwatch-auto-alarms.zip** file to the S3 bucket you created earlier.  You can use the following command (Note: The Account ID is omitted):

    aws s3 cp amazon-cloudwatch-auto-alarms.zip s3://amazon-cloudwatch-auto-alarms-bucket-<account id omitted>

7.	You can now use the CloudWatchAutoAlarms CloudFormation template to deploy the Lambda function across multiple regions and accounts in your AWS Organization.  This walkthrough deploys a service managed CloudFormation StackSet in the AWS Organizations master account.  You must also specify the account ID where the S3 deployment bucket was created so the same S3 bucket is used across account deployments in your organization.  Use the following command to deploy the service managed CloudFormation StackSet:

    aws cloudformation create-stack-set --stack-set-name amazon-cloudwatch-auto-alarms --template-body file://CloudWatchAutoAlarms.yaml --parameters ParameterKey=S3DeploymentBucketAccountId,ParameterValue=<account id omitted> --capabilities CAPABILITY_NAMED_IAM --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false --permission-model SERVICE_MANAGED --region us-east-1

8.	 After the StackSet is created, you can specify which AWS accounts and regions the StackSet should be deployed.  For service managed StackSets, you specify your AWS Organization ID or AWS Organizational Unit IDs gain order to deploy the lambda function to all current and future accounts within them.   Use the following AWS CLI command to deploy the StackSet to your organization / organizational units (Note:  The organization id is omitted from the example and the us-east-1 region is used):

    aws cloudformation create-stack-instances --stack-set-name amazon-cloudwatch-auto-alarms --deployment-targets OrganizationalUnitIds=<Root Organization ID omitted> --regions us-east-1 --operation-id amazon-cloudwatch-auto-alarms-deployment-1 --region us-east-1

You can monitor the progress and status of the StackSet operation in the AWS CloudFormation service console.  

Once the deployment is complete, the status will change from **RUNNING** to **SUCCEEDED**.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
