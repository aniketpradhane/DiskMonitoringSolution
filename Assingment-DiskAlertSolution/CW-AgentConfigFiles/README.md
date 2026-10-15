# Amazon CloudWatch Agent Configuration — Linux and Windows

## Overview

This directory contains the Amazon CloudWatch Agent configuration files used to collect disk utilization metrics from Linux and Windows EC2 instances.

The collected metrics are published to the `Enterprise/DiskMonitoring` CloudWatch namespace. The central disk monitoring Lambda uses these metrics to create and update CloudWatch alarms across linked AWS accounts.

## Files

```text
config/
├── linux-cloudwatch-agent.json
└── windows-cloudwatch-agent.json
```

| File | Purpose |
|---|---|
| `linux-cloudwatch-agent.json` | Collects filesystem utilization metrics from Linux instances. |
| `windows-cloudwatch-agent.json` | Collects logical disk metrics from Windows instances. |

## Metrics Collected

### Linux

The Linux configuration collects the following metrics from mounted filesystems:

| Metric | Description |
|---|---|
| `used_percent` | Percentage of filesystem space used. |
| `free` | Available filesystem space in bytes. |
| `total` | Total filesystem capacity in bytes. |

The configuration monitors eligible filesystems and excludes temporary, virtual, and system filesystem types that are not relevant for normal disk capacity monitoring.

### Windows

The Windows configuration collects the following metrics from logical disks:

| Metric | Description |
|---|---|
| `% Free Space` | Percentage of available space on a logical disk. |
| `Free Megabytes` | Available disk space in megabytes. |

The configuration collects metrics for the logical disks reported by Windows, allowing each disk to be monitored separately.

## CloudWatch Configuration

Both configurations publish metrics to the following namespace:

```text
Enterprise/DiskMonitoring
```

The configurations also add instance dimensions, including:

- `InstanceId`
- `InstanceType`

Metrics are collected every 60 seconds.

The Linux configuration runs the agent as root to allow access to filesystem statistics. The Windows configuration collects logical disk metrics through the CloudWatch Agent.

## Prerequisites

Before applying the configuration, ensure that:

- The EC2 instance has the CloudWatch Agent installed.
- The instance has an IAM role with permission to publish CloudWatch metrics.
- The instance can reach the CloudWatch monitoring endpoint in its Region, either through network connectivity or an appropriate VPC endpoint.
- The configuration file is available on the instance.
- The CloudWatch Agent service is running.

For private subnets, configure the required network connectivity and VPC endpoints according to your environment.

## Installation

### Linux

Install the CloudWatch Agent using AWS Systems Manager Distributor or the appropriate package for the operating system.

Copy `linux-cloudwatch-agent.json` to the instance, for example:

```bash
sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc/
```

Place the configuration file at:

```text
/opt/aws/amazon-cloudwatch-agent/etc/linux-cloudwatch-agent.json
```

Apply the configuration:

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/linux-cloudwatch-agent.json \
  -s
```

Check the agent status:

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a status
```

### Windows

Install the CloudWatch Agent using AWS Systems Manager Distributor or the appropriate AWS installation package.

Copy `windows-cloudwatch-agent.json` to the instance, for example:

```text
C:\ProgramData\Amazon\AmazonCloudWatchAgent\windows-cloudwatch-agent.json
```

Open PowerShell as Administrator and apply the configuration:

```powershell
& "$env:ProgramFiles\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" `
  -a fetch-config `
  -m ec2 `
  -c file:"C:\ProgramData\Amazon\AmazonCloudWatchAgent\windows-cloudwatch-agent.json" `
  -s
```

Check the agent status:

```powershell
& "$env:ProgramFiles\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" `
  -a status
```

The commands above assume the standard CloudWatch Agent installation paths. Adjust the paths if the agent is installed elsewhere.

## IAM Permissions

The EC2 instance role must allow the CloudWatch Agent to publish metrics. The AWS-managed `CloudWatchAgentServerPolicy` is a common starting point.

Attach it to the EC2 instance role, or use an equivalent custom policy that grants the required permissions.

Do not place AWS access keys or credentials in the configuration files.

## Validation

After starting the agent, open the CloudWatch console and navigate to:

**CloudWatch → Metrics → All metrics → `Enterprise/DiskMonitoring`**

Verify that metrics are available for the expected instance IDs and filesystems or logical disks.

Allow time for the agent to publish metrics and for CloudWatch to display them.

You can also review the agent logs if metrics are missing.

### Linux log location

```text
/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

### Windows log location

```text
C:\ProgramData\Amazon\AmazonCloudWatchAgent\Logs\amazon-cloudwatch-agent.log
```

## Integration with Disk Monitoring Lambda

The central Lambda discovers metrics from the `Enterprise/DiskMonitoring` namespace through CloudWatch cross-account observability.

The current alarm logic uses:

| Operating system | Metric | Warning | Critical |
|---|---|---:|---:|
| Linux | `used_percent` | >= 85% | >= 95% |
| Windows | `% Free Space` | <= 15% | <= 5% |

The `free`, `total`, and `Free Megabytes` metrics are collected for visibility and can be used for additional absolute free-space thresholds in a future enhancement.

## Operational Notes

- The configuration collects metrics every 60 seconds. Review CloudWatch metric and alarm costs before deploying across a large fleet.
- Linux filesystem exclusions can be adjusted to match the operating systems and mount points used in your environment.
- Windows logical disk monitoring should be validated on representative server types before broad deployment.
- The CloudWatch Agent should be deployed and configured through a consistent mechanism, such as Systems Manager State Manager, Ansible, or your existing configuration management process.
- Store and manage configuration changes through version control.
- Test changes on a small group of Linux and Windows instances before rolling them out across production accounts.

## Summary

These configuration files standardize disk metric collection across Linux and Windows EC2 instances. They provide the metrics required by the central disk monitoring solution, allowing CloudWatch alarms to be managed centrally across linked AWS accounts.
