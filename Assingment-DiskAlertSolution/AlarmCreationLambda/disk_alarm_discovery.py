
import os
import re
import json
import hashlib
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NAMESPACE = os.environ.get(
    "METRIC_NAMESPACE", "Enterprise/DiskMonitoring"
)
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
PERIOD = int(os.environ.get("ALARM_PERIOD_SECONDS", "300"))
EVALUATION_PERIODS = int(os.environ.get("EVALUATION_PERIODS", "2"))

cloudwatch = boto3.client("cloudwatch")

# Warning and critical thresholds.
# Linux: high used percentage is bad.
# Windows: low free percentage is bad.
METRIC_RULES = {
    "used_percent": [
        ("Warning", 85.0, "GreaterThanOrEqualToThreshold"),
        ("Critical", 95.0, "GreaterThanOrEqualToThreshold"),
    ],
    "% Free Space": [
        ("Warning", 15.0, "LessThanOrEqualToThreshold"),
        ("Critical", 5.0, "LessThanOrEqualToThreshold"),
    ],
}


def build_alarm_name(account_id, metric_name, dimensions, severity):
    """Create a stable name unique to account, metric, and disk."""
    dim_key = json.dumps(
        sorted(
            (d["Name"], d["Value"])
            for d in dimensions
        ),
        separators=(",", ":"),
    )
    digest = hashlib.sha256(
        f"{account_id}|{metric_name}|{dim_key}".encode()
    ).hexdigest()[:16]

    safe_metric = re.sub(
        r"[^A-Za-z0-9_-]", "-", metric_name
    )[:30]

    return f"Disk-{account_id}-{safe_metric}-{severity}-{digest}"


def create_alarm(account_id, metric):
    metric_name = metric["MetricName"]
    if metric_name not in METRIC_RULES:
        return False

    dimensions = metric.get("Dimensions", [])

    # Require an instance identifier so the alarm targets a VM.
    if not any(
        d["Name"] == "InstanceId" for d in dimensions
    ):
        logger.warning(
            "Skipping metric without InstanceId: account=%s metric=%s",
            account_id, metric_name
        )
        return False

    # MetricDataQueries enables a central alarm to watch a
    # metric owned by a linked source account.
    query = {
        "Id": "diskmetric",
        "ReturnData": True,
        "MetricStat": {
            "Metric": {
                "Namespace": NAMESPACE,
                "MetricName": metric_name,
                "Dimensions": dimensions,
                "AccountId": account_id,
            },
            "Period": PERIOD,
            "Stat": "Average",
        },
    }

    for severity, threshold, comparison in METRIC_RULES[metric_name]:
        alarm_name = build_alarm_name(
            account_id, metric_name, dimensions, severity
        )

        request = {
            "AlarmName": alarm_name,
            "AlarmDescription": (
                f"{severity} disk alarm; source account={account_id}; "
                f"metric={metric_name}; "
                f"dimensions={json.dumps(dimensions, sort_keys=True)}"
            ),
            "MetricDataQueries": [query],
            "EvaluationPeriods": EVALUATION_PERIODS,
            "DatapointsToAlarm": EVALUATION_PERIODS,
            "Threshold": threshold,
            "ComparisonOperator": comparison,
            "TreatMissingData": "missing",
            "ActionsEnabled": bool(SNS_TOPIC_ARN),
        }

        if SNS_TOPIC_ARN:
            request["AlarmActions"] = [SNS_TOPIC_ARN]

        # Stable AlarmName makes repeated runs idempotent:
        # CloudWatch creates the alarm or updates its definition.
        cloudwatch.put_metric_alarm(**request)

        logger.info(
            "Alarm created/updated: %s (account=%s)",
            alarm_name, account_id
        )

    return True


def lambda_handler(event, context):
    """Discover OAM-linked metrics and create central alarms."""
    results = {
        "metrics_seen": 0,
        "alarms_processed": 0,
        "errors": [],
    }

    paginator = cloudwatch.get_paginator("list_metrics")

    for page in paginator.paginate(
        Namespace=NAMESPACE,
        IncludeLinkedAccounts=True,
    ):
        metrics = page.get("Metrics", [])
        owners = page.get("OwningAccounts", [])

        # AWS returns a 1:1 mapping between metrics and owners.
        if len(metrics) != len(owners):
            raise RuntimeError(
                "CloudWatch returned mismatched metric/owner arrays"
            )

        for metric, account_id in zip(metrics, owners):
            results["metrics_seen"] += 1

            try:
                if create_alarm(account_id, metric):
                    results["alarms_processed"] += len(
                        METRIC_RULES[metric["MetricName"]]
                    )
            except ClientError as exc:
                error = {
                    "account_id": account_id,
                    "metric_name": metric.get("MetricName"),
                    "error": exc.response["Error"]["Code"],
                }
                results["errors"].append(error)
                logger.exception(
                    "Failed processing metric for account %s",
                    account_id,
                )

    logger.info("Discovery result: %s", json.dumps(results))
    return results
