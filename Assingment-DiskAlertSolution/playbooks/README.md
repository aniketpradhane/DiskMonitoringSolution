# AWS Disk Monitoring — Ansible Automation

## Overview

This repository contains Ansible playbooks to deploy and maintain the Amazon CloudWatch Agent on Linux and Windows EC2 instances.

The playbooks discover running EC2 instances dynamically using AWS tags, check their Systems Manager (SSM) connectivity, and execute the appropriate installation or configuration process based on the operating system.

The CloudWatch Agent collects disk utilization metrics and publishes them to the `Enterprise/DiskMonitoring` CloudWatch namespace. These metrics are consumed by the centralized disk monitoring solution to create alarms and notify the support team when disk space reaches the configured thresholds.

The solution is designed for AWS environments where instances are distributed across multiple workload accounts and managed through a central automation process.

## Repository Structure

```text
ansible/
├── playbooks/
│   ├── disk-monitoring.yml
│   └── reconcile-instance.yml
├── README.md
```

The main playbook discovers the target instances and prepares the required artifact URLs. The per-instance task file checks SSM status and executes the relevant actions for each discovered instance.

## How It Works

1. Ansible verifies the AWS identity used to run the automation.
2. The playbook discovers running EC2 instances tagged `DiskMonitoring=Enabled`.
3. It generates temporary pre-signed S3 URLs for the CloudWatch Agent installers and configuration files.
4. Each discovered instance is passed to `reconcile-instance.yml`.
5. The per-instance task checks whether the instance is available through AWS Systems Manager.
6. If the instance is online in SSM, the appropriate Linux or Windows commands are executed to install or configure the CloudWatch Agent.
7. The agent publishes disk metrics to CloudWatch for centralized monitoring.

Instances that are not online in SSM are reported as failures rather than being silently skipped.

## AWS Resources Used

| Resource | Purpose |
|---|---|
| Amazon EC2 | Hosts the Linux and Windows workloads. |
| AWS Systems Manager | Executes commands on managed instances. |
| Amazon S3 | Stores CloudWatch Agent installers and configuration files. |
| Amazon CloudWatch | Receives disk metrics and evaluates alarms. |
| AWS IAM | Controls access to EC2, S3, SSM, and CloudWatch. |
| Ansible | Coordinates instance discovery and agent deployment. |

## Instance Selection

The playbook discovers instances using the following configuration:

```yaml
aws_region: ap-south-1

target_tag_key: DiskMonitoring
target_tag_value: Enabled
```

Only instances that are in the `running` state and have the matching tag are selected.

To onboard an instance, apply the following EC2 tag:

```text
Key:   DiskMonitoring
Value: Enabled
```

No instance IDs need to be maintained manually. Newly tagged running instances are picked up during subsequent playbook executions.

The current discovery configuration targets the AWS Region specified by `aws_region`. To monitor other Regions or AWS accounts, extend the discovery and execution workflow accordingly.

## S3 Artifact Configuration

The CloudWatch Agent installers and configuration files are stored in a centrally managed S3 bucket.

Example configuration:

```yaml
config_bucket: company-shared-monitoring-artifacts

linux_rpm_key: cloudwatch-agent/linux/amazon-cloudwatch-agent.rpm
linux_deb_key: cloudwatch-agent/linux/amazon-cloudwatch-agent.deb
windows_msi_key: cloudwatch-agent/windows/amazon-cloudwatch-agent.msi

linux_config_key: config/linux-cloudwatch-agent.json
windows_config_key: config/windows-cloudwatch-agent.json
```

The playbook generates pre-signed URLs for these artifacts so that the instance-side commands can download the required files without embedding permanent AWS credentials in the scripts.

The default URL expiry is 900 seconds (15 minutes).

Ensure that the S3 objects exist at the configured keys and that the identity generating the URLs has permission to access them. The instance-side download process must complete before the URLs expire.

## Prerequisites

Before running the playbook, ensure that:

- Ansible is installed on the automation host.
- The AWS CLI is installed and configured.
- The execution identity can call `sts:GetCallerIdentity` and discover the target EC2 instances.
- The execution identity can generate pre-signed URLs for the required S3 objects.
- The required CloudWatch Agent installers and configuration files are available in S3.
- Target instances are managed by AWS Systems Manager.
- SSM Agent is installed and running on the target instances.
- Target instances have the required IAM permissions and network connectivity for SSM operations.
- The automation has permission to send commands and retrieve command results through SSM.

The exact IAM permissions depend on the implementation of `reconcile-instance.yml` and the scripts it invokes.

## Configuration

The main playbook defines the following settings:

| Variable | Default | Description |
|---|---|---|
| `aws_region` | `ap-south-1` | Region used for EC2 discovery and SSM operations. |
| `s3_region` | `ap-south-1` | Region containing the artifact bucket. |
| `target_tag_key` | `DiskMonitoring` | EC2 tag key used for instance selection. |
| `target_tag_value` | `Enabled` | Required EC2 tag value. |
| `config_bucket` | `company-shared-monitoring-artifacts` | S3 bucket containing installers and configurations. |
| `presigned_url_expiry` | `900` | Pre-signed URL validity in seconds. |
| `ssm_timeout_seconds` | `600` | Intended timeout for SSM command execution. |
| `poll_retries` | `36` | Intended number of command-status polling attempts. |
| `poll_delay_seconds` | `10` | Intended delay between polling attempts. |

The SSM timeout and polling variables must be used by the reconciliation tasks for them to take effect.

## Running the Playbook

Run the main playbook from the repository root:

```bash
ansible-playbook playbooks/disk-monitoring.yml
```

The playbook uses the AWS CLI credentials available to the automation process. Run it under the approved automation identity and verify the AWS account and Region before execution.

To check the AWS identity manually:

```bash
aws sts get-caller-identity
```

To validate instance discovery independently:

```bash
aws ec2 describe-instances \
  --region ap-south-1 \
  --filters \
    "Name=instance-state-name,Values=running" \
    "Name=tag:DiskMonitoring,Values=Enabled" \
  --query "Reservations[].Instances[].InstanceId" \
  --output json
```

## Linux and Windows Handling

The per-instance reconciliation tasks should identify the operating system and select the appropriate installer and configuration file.

| Operating system | Installer | Configuration |
|---|---|---|
| Linux — RPM-based | `amazon-cloudwatch-agent.rpm` | `linux-cloudwatch-agent.json` |
| Linux — Debian-based | `amazon-cloudwatch-agent.deb` | `linux-cloudwatch-agent.json` |
| Windows | `amazon-cloudwatch-agent.msi` | `windows-cloudwatch-agent.json` |

After installation or configuration updates, the tasks should ensure that the CloudWatch Agent service is running.

The exact installation commands and operating-system detection logic are maintained in `reconcile-instance.yml` and its associated scripts.

## Disk Metrics

The CloudWatch Agent configurations publish metrics to:

```text
Enterprise/DiskMonitoring
```

### Linux metrics

- `used_percent`
- `free`
- `total`

### Windows metrics

- `% Free Space`
- `Free Megabytes`

These metrics are used by the central monitoring Lambda to create or update disk utilization alarms.

| Operating system | Severity | Threshold |
|---|---|---|
| Linux | Warning | Disk usage >= 85% |
| Linux | Critical | Disk usage >= 95% |
| Windows | Warning | Free space <= 15% |
| Windows | Critical | Free space <= 5% |

The thresholds are maintained in the central Lambda and can be changed independently of the Ansible deployment.

## Error Handling

The playbook is intended to report failures during instance reconciliation, including instances that are not online in SSM.

When a deployment fails, check:

- Whether the instance is running and tagged correctly.
- Whether the instance appears as an SSM managed node and is online.
- Whether the execution identity has the required SSM permissions.
- Whether the instance can reach the required SSM and S3 endpoints.
- Whether the S3 objects exist and the pre-signed URLs are still valid.
- Whether the installation or configuration commands completed successfully.

Review the Ansible output and SSM command status to identify the failure.

## Security Considerations

- Use a dedicated automation identity with least-privilege permissions.
- Restrict EC2 discovery and SSM command execution to approved accounts and instances.
- Keep S3 artifacts private and use short-lived pre-signed URLs.
- Protect the Ansible execution environment and its AWS credentials.
- Use an encrypted S3 bucket and enforce appropriate access controls.
- Avoid logging pre-signed URLs because they provide temporary access to the associated objects.
- Keep installers and configuration files version-controlled and validate them before deployment.
- Use the existing AWS Landing Zone and AFT processes to maintain consistent access and onboarding controls.

## Operational Considerations

**New instances:** Apply the required EC2 tag to include an instance in the monitoring deployment.

**Repeated execution:** The reconciliation tasks should be idempotent so that repeated runs do not unnecessarily reinstall the agent or restart the service.

**SSM availability:** Instances that are offline in SSM should be reported for investigation and retried during a later run when appropriate.

**Artifact management:** Keep installer versions and configuration changes controlled. Validate updates in a non-production environment before wider deployment.

**Scale:** For large fleets, execute deployments in controlled batches and review Ansible execution time, SSM command quotas, and AWS API throttling.

**Multi-account support:** The current playbook discovers instances using the AWS identity and Region configured for the run. Cross-account role assumption or a separate orchestration mechanism is required if the automation must discover and manage instances across multiple accounts.

## Integration with Central Monitoring

The Ansible automation handles agent installation and configuration. Alarm management is handled separately by the central Monitoring account.

The overall flow is:

1. Ansible discovers and reconciles eligible EC2 instances.
2. The CloudWatch Agent publishes disk metrics.
3. CloudWatch OAM provides cross-account metric visibility.
4. The central Lambda discovers metrics and creates or updates alarms.
5. CloudWatch alarms send notifications through SNS when thresholds are breached.

## Future Enhancements

- Add multi-account and multi-Region discovery.
- Add automatic retries for temporary SSM failures.
- Produce a deployment summary showing successful and failed instances.
- Add CloudWatch Agent version checks and controlled upgrades.
- Integrate the playbook with the AFT account onboarding process.
- Add automated validation that expected disk metrics are being published.
- Add scheduled execution through the organization's approved automation platform.

## Summary

This Ansible workflow provides tag-based discovery and automated CloudWatch Agent reconciliation for Linux and Windows EC2 instances. It uses centrally managed S3 artifacts and AWS Systems Manager to simplify deployment without maintaining static instance lists.

The workflow can be extended to support additional AWS accounts and Regions as part of the enterprise disk monitoring solution.
