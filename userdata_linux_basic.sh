#!/usr/bin/env bash
# comment out the appropriate linux version for install
source /etc/os-release
if [[ $ID == 'amzn' ]] ; then
  # Amazon Linux
  wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm -O /tmp/cwagent.rpm
  yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
  systemctl enable amazon-ssm-agent
  systemctl restart amazon-ssm-agent

elif [[ $ID == 'rhel' ]]; then
  # Redhat
  curl -o /tmp/cwagent.rpm https://s3.amazonaws.com/amazoncloudwatch-agent/redhat/amd64/latest/amazon-cloudwatch-agent.rpm
  yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
  systemctl enable amazon-ssm-agent
  systemctl restart amazon-ssm-agent
elif [[ $ID == 'sles' ]]; then
  # SUSE
  wget https://s3.amazonaws.com/amazoncloudwatch-agent/suse/amd64/latest/amazon-cloudwatch-agent.rpm -O /tmp/cwagent.rpm
  wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
  rpm --install amazon-ssm-agent.rpm
  systemctl enable amazon-ssm-agent
  systemctl restart amazon-ssm-agent

elif [[ $ID == 'debian' ]]; then
  # Debian
  wget https://s3.amazonaws.com/amazoncloudwatch-agent/debian/amd64/latest/amazon-cloudwatch-agent.deb -O /tmp/cwagent.deb
  wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
  dpkg -i amazon-ssm-agent.deb
  systemctl enable amazon-ssm-agent
  systemctl restart amazon-ssm-agent
elif [[ $ID == 'ubuntu' ]] ; then
  # Ubuntu
   curl -o /tmp/cwagent.deb https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
   snap switch --channel=candidate amazon-ssm-agent
   sudo snap install amazon-ssm-agent --classic
  systemctl enable amazon-ssm-agent
  systemctl enable  snap.amazon-ssm-agent.amazon-ssm-agent.service
  systemctl restart  snap.amazon-ssm-agent.amazon-ssm-agent.service

fi

if [[ $ID_LIKE == 'fedora' ]] || [[ $ID_LIKE == 'suse'  ]]; then
  # For RPM install, uncoment next line
  rpm -U /tmp/cwagent.rpm
elif [[ $ID_LIKE == 'debian' ]] || [[ $ID == 'debian'  ]]; then
  # For Debian package install, uncoment next line
  dpkg -i -E ./cwagent.deb
fi

cat > /tmp/cwconfig.json <<"EOL"
{
	"agent": {
		"metrics_collection_interval": 60,
		"run_as_user": "root"
	},
	"metrics": {
		"append_dimensions": {
			"AutoScalingGroupName": "${aws:AutoScalingGroupName}",
			"ImageId": "${aws:ImageId}",
			"InstanceId": "${aws:InstanceId}",
			"InstanceType": "${aws:InstanceType}"
		},
		"metrics_collected": {
			"disk": {
				"measurement": [
					"used_percent"
				],
				"metrics_collection_interval": 60,
				"resources": [
					"*"
				]
			},
			"mem": {
				"measurement": [
					"mem_used_percent"
				],
				"metrics_collection_interval": 60
			}
		}
	}
}
EOL
echo "Configuring CloudWatch agent with file /tmp/cwconfig.json: "
cat /tmp/cwconfig.json
echo "starting cloudwatch agent"
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/tmp/cwconfig.json -s
