# AWS Central Disk Monitoring

## Overview

This project automates disk space monitoring for Linux and Windows EC2 instances running across multiple AWS accounts.

The solution uses Amazon CloudWatch to collect disk metrics, AWS Lambda to create and update alarms, EventBridge to run the discovery process periodically, and SNS to send alerts when disk utilization crosses the configured threshold.

The monitoring components are deployed in a central Monitoring account. Workload accounts are onboarded through AWS Control Tower and Account Factory for Terraform (AFT).

The aim is to identify disk space issues before they cause application failures or service downtime.

## Architecture

```text
AWS Organization
       |
       +--------------------+
       |                    |
 Workload Account 1    Workload Account 2
       |                    |
 Linux / Windows EC2   Linux / Windows EC2
       |                    |
 CloudWatch Agent      CloudWatch Agent
       |                    |
       +---------+----------+
                 |
       CloudWatch Disk Metrics
                 |
      OAM Cross-Account Links
                 |
        Monitoring Account
                 |
          EventBridge
                 |
            AWS Lambda
                 |
       CloudWatch Alarms
                 |
             Amazon SNS
                 |
         Email Notifications
```

## AWS Services Used

| Service | Purpose |
|---|---|
| Amazon CloudWatch Agent | Collects disk metrics from EC2 instances. |
| Amazon CloudWatch | Stores metrics and evaluates alarms. |
| CloudWatch OAM | Provides access to metrics from linked accounts. |
| AWS Lambda | Discovers metrics and creates or updates alarms. |
| Amazon EventBridge | Runs the Lambda function on a schedule. |
| Amazon SNS | Sends notifications when an alarm is triggered. |
| AWS AFT | Supports account onboarding and OAM link configuration. |

## Repository Structure

```text
aws-central-disk-monitoring/
├── lambda/
│   └── disk_alarm_discovery.py
├── config/
│   ├── linux-cloudwatch-agent.json
│   └── windows-cloudwatch-agent.json
├── iam/
│   └── lambda-execution-policy.json
├── terraform/
│   └── README.md
└── README.md
```

## How It Works

1. The CloudWatch Agent collects disk metrics from Linux and Windows EC2 instances.
2. Metrics are published to the `Enterprise/DiskMonitoring` namespace.
3. CloudWatch OAM links allow the Monitoring account to discover metrics from workload accounts.
4. EventBridge invokes the Lambda function every five minutes.
5. Lambda discovers the available disk metrics and identifies the account that owns each metric.
6. The function creates or updates CloudWatch alarms based on the configured thresholds.
7. CloudWatch sends notifications to the central SNS topic when an alarm enters the ALARM state.

Alarm names are generated consistently using the account ID, metric name, disk dimensions, and severity. This prevents duplicate alarms from being created on every scheduled execution.

## Disk Metrics and Thresholds

### Linux

The CloudWatch Agent collects the following metrics:

- `used_percent` — percentage of filesystem space used.
- `free` — free filesystem space.
- `total` — total filesystem capacity.

### Windows

The CloudWatch Agent collects:

- `% Free Space` — percentage of free space on a logical disk.
- `Free Megabytes` — available disk space in megabytes.

### Alarm Configuration

| OS | Metric | Severity | Threshold |
|---|---|---|---|
| Linux | `used_percent` | Warning | >= 85% |
| Linux | `used_percent` | Critical | >= 95% |
| Windows | `% Free Space` | Warning | <= 15% |
| Windows | `% Free Space` | Critical | <= 5% |

The current Lambda implementation creates alarms for `used_percent` and `% Free Space`. The absolute free-space metrics are collected but are not yet used for alarm creation.

Thresholds can be changed in the `METRIC_RULES` dictionary in `disk_alarm_discovery.py`.

## Prerequisites

Before deploying the solution, ensure that:

- The AWS Organization and central Monitoring account are available.
- An OAM sink is configured in the Monitoring account.
- Workload accounts have OAM links for `AWS::CloudWatch::Metric`.
- Linux and Windows EC2 instances have the CloudWatch Agent installed and configured.
- EC2 instance roles can publish the required CloudWatch metrics.
- The Lambda execution role has the required permissions.
- A central SNS topic and its notification subscriptions are configured.
- The monitoring components are deployed in the Region where the metrics are published.

For additional Regions, configure the corresponding OAM sink and links and deploy or extend the monitoring components for those Regions.

## Lambda Configuration

Configure the following environment variables on the Lambda function.

| Variable | Example | Description |
|---|---|---|
| `METRIC_NAMESPACE` | `Enterprise/DiskMonitoring` | Namespace used by the CloudWatch Agent. |
| `SNS_TOPIC_ARN` | `arn:aws:sns:eu-west-2:123456789012:disk-monitoring-alerts` | Central SNS topic ARN. |
| `ALARM_PERIOD_SECONDS` | `300` | Alarm evaluation period in seconds. |
| `EVALUATION_PERIODS` | `2` | Number of evaluation periods. |

Replace the example ARN with the actual SNS topic ARN.

## IAM Permissions

The Lambda execution role requires permissions to discover metrics, create or update alarms, and write logs.

The main permissions are:

```text
cloudwatch:ListMetrics
cloudwatch:PutMetricAlarm
logs:CreateLogStream
logs:PutLogEvents
```

The role also needs the standard Lambda logging permissions appropriate to your deployment.

Since the solution uses CloudWatch OAM, Lambda does not need to assume an IAM role in each workload account or call AWS Organizations to list accounts.

Review and restrict permissions according to your organization's IAM standards.

## Deployment

### 1. Package the Lambda function

```bash
cd lambda
zip disk-alarm-discovery.zip disk_alarm_discovery.py
```

### 2. Create the execution role

Create an IAM role trusted by the Lambda service and attach the required permissions.

### 3. Deploy the Lambda function

Upload the ZIP package and configure the handler:

```text
disk_alarm_discovery.lambda_handler
```

Configure the environment variables listed above.

### 4. Configure EventBridge

Create a scheduled rule to invoke Lambda every five minutes:

```text
rate(5 minutes)
```

Configure the Lambda function as the target and allow EventBridge to invoke it.

### 5. Configure SNS

Set the central SNS topic ARN in the Lambda environment variables. Confirm the required subscriptions before testing notifications.

CloudWatch alarms publish notifications directly to SNS, so the Lambda function does not need `sns:Publish` permission for this workflow.

### 6. Test the function

Invoke Lambda manually with the following test event:

```json
{}
```

Check the Lambda execution result and CloudWatch Logs to confirm that metrics are discovered and alarms are created or updated.

## Validation

Before onboarding all workload accounts, verify the following:

- [ ] Linux instances publish `used_percent`.
- [ ] Windows instances publish `% Free Space`.
- [ ] OAM links are configured correctly.
- [ ] Lambda discovers metrics from the expected accounts.
- [ ] CloudWatch alarms are created with the correct thresholds.
- [ ] Repeated Lambda executions update existing alarms.
- [ ] SNS notifications are received when a threshold is breached.
- [ ] Alarm recovery works when disk utilization returns to normal.
- [ ] Missing metrics and agent failures are handled appropriately.

## Operational Considerations

**Metric discovery:** Newly published metrics may take up to 15 minutes to appear in `ListMetrics`. The five-minute schedule does not guarantee immediate discovery.

**Missing metrics:** The current alarms use `TreatMissingData = missing`. If an instance stops publishing metrics, its disk alarm may enter `INSUFFICIENT_DATA`. A separate check is recommended for CloudWatch Agent health.

**Alarm evaluation:** With a five-minute period and two evaluation periods, the alarm checks two consecutive five-minute periods when configured for two out of two datapoints.

**Cost:** CloudWatch custom metrics and alarms can generate significant costs in large environments. Each monitored disk or filesystem can produce multiple alarms, so review the expected alarm count before onboarding a large fleet.

**Scale:** For environments with thousands of instances or large numbers of filesystems, monitor Lambda execution duration and errors. The discovery process may need to be split by Region or handled through a distributed workflow.

**Security:** Keep monitoring resources in the central account, use least-privilege IAM policies, restrict OAM access to the intended AWS Organization, and manage account configuration through Terraform and AFT.

## Future Improvements

- Add absolute free-space thresholds for Linux and Windows.
- Add monitoring for CloudWatch Agent failures.
- Include application and environment details in alarm descriptions.
- Remove alarms for terminated instances and disks that are no longer monitored.
- Add Terraform modules for the complete deployment.
- Extend the solution to cover multiple AWS Regions.
- Introduce distributed processing for very large environments.

## Summary

This solution provides centralized disk monitoring for Linux and Windows EC2 instances across multiple AWS accounts. CloudWatch Agent collects the metrics, OAM enables cross-account discovery, Lambda manages the alarms, EventBridge schedules the process, and SNS handles notifications.

The design can be integrated with the existing AWS Landing Zone and AFT onboarding process, making it easier to apply consistent disk monitoring as new accounts and workloads are added.
