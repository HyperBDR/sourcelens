"""
Celery beat task: aggregate LLMUsage into LLMUsageSeries.

Registered as agentcore_metering.adapters.django.tasks.aggregate.
aggregate_llm_usage_series_task. Run with granularity=hour|day|month.
Uses agentcore_task TaskTracker so runs are recorded in TaskExecution.
"""
import logging
import traceback as tb
from datetime import date, datetime, timedelta, timezone as utc_tz
from typing import Optional

from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from agentcore_metering.adapters.django.conf import get_aggregation_timezone
from agentcore_metering.adapters.django.services.usage_chart_series import (
    SERIES_GRANULARITY_DAY,
    SERIES_GRANULARITY_HOUR,
    SERIES_GRANULARITY_MONTH,
    aggregate_usage_to_series,
)
from agentcore_metering.adapters.django.services.usage_aggregation import (
    _ensure_aware_datetime,
)

logger = logging.getLogger(__name__)


def _agg_tz():
    """
    Return ZoneInfo for aggregation timezone (e.g. Asia/Shanghai).
    NOTE(Ray): Lazy import to avoid loading zoneinfo at module import.
    Falls back to UTC on ImportError or invalid timezone name.
    """
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        return ZoneInfo(get_aggregation_timezone())
    except (ImportError, ZoneInfoNotFoundError):
        return utc_tz.utc


def _default_range(granularity: str):
    """
    Return (start_date, end_date) for the given granularity when not provided.
    hour: last 2 hours (UTC). day/month: yesterday/last month in aggregation
    timezone, then converted to UTC for DB query.
    """
    now = timezone.now()
    if granularity == SERIES_GRANULARITY_HOUR:
        end_date = now
        start_date = end_date - timedelta(hours=2)
        return start_date, end_date

    tz = _agg_tz()
    now_in_tz = now.astimezone(tz)

    if granularity == SERIES_GRANULARITY_DAY:
        yesterday = (now_in_tz.date() - timedelta(days=1))
        start_local = datetime.combine(
            yesterday, datetime.min.time(), tzinfo=tz
        )
        end_local = datetime.combine(
            yesterday,
            datetime.max.time().replace(microsecond=999999),
            tzinfo=tz,
        )
        start_date = start_local.astimezone(utc_tz.utc)
        end_date = end_local.astimezone(utc_tz.utc)
        return start_date, end_date

    if granularity == SERIES_GRANULARITY_MONTH:
        first_this_month = date(now_in_tz.year, now_in_tz.month, 1)
        last_day_prev = first_this_month - timedelta(days=1)
        first_prev_month = last_day_prev.replace(day=1)
        start_local = datetime.combine(
            first_prev_month, datetime.min.time(), tzinfo=tz
        )
        end_local = datetime.combine(
            last_day_prev,
            datetime.max.time().replace(microsecond=999999),
            tzinfo=tz,
        )
        start_date = start_local.astimezone(utc_tz.utc)
        end_date = end_local.astimezone(utc_tz.utc)
        return start_date, end_date

    end_date = now
    start_date = end_date - timedelta(days=1)
    return start_date, end_date


def _run_one_granularity(granularity: str, start_date=None, end_date=None):
    """Run aggregation for one granularity; return upserted count."""
    if start_date and end_date:
        start_dt = parse_datetime(start_date)
        end_dt = parse_datetime(end_date)
        if start_dt and end_dt:
            start_dt = _ensure_aware_datetime(start_dt)
            end_dt = _ensure_aware_datetime(end_dt)
        else:
            start_dt, end_dt = _default_range(granularity)
    else:
        start_dt, end_dt = _default_range(granularity)
    return aggregate_usage_to_series(
        granularity=granularity,
        start_date=start_dt,
        end_date=end_dt,
    )


TASK_NAME_AGGREGATE = (
    "agentcore_metering.adapters.django.tasks.aggregate."
    "aggregate_llm_usage_series_task"
)
MODULE_AGENTCORE_METERING = "agentcore_metering"


@shared_task(
    name=TASK_NAME_AGGREGATE,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
def aggregate_llm_usage_series_task(
    self,
    granularity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Aggregate LLMUsage into LLMUsageSeries. When granularity is omitted
    (e.g. from beat), run hour + day + month in one go. Otherwise run
    the given granularity only. Registers this run in TaskExecution.
    """
    from agentcore_task.adapters.django.services.task_tracker import (
        TaskTracker,
        register_task_execution,
    )
    from agentcore_task.constants import TaskStatus

    task_id = self.request.id
    register_task_execution(
        task_id=task_id,
        task_name=TASK_NAME_AGGREGATE,
        module=MODULE_AGENTCORE_METERING,
        metadata={
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
        },
        initial_status=TaskStatus.STARTED,
    )
    if granularity is None or granularity == "":
        logger.info(
            "Starting aggregate_llm_usage_series_task (all granularities)"
        )
        total = 0
        try:
            for gran in (
                SERIES_GRANULARITY_HOUR,
                SERIES_GRANULARITY_DAY,
                SERIES_GRANULARITY_MONTH,
            ):
                n = _run_one_granularity(gran)
                total += n
                logger.info(f"aggregate granularity={gran} upserted={n}")
            out = {"upserted": total, "granularity": "all"}
            TaskTracker.update_task_status(
                task_id, TaskStatus.SUCCESS, result=out
            )
            logger.info(
                f"Finished aggregate_llm_usage_series_task total_upserted={total}"
            )
            return out
        except Exception as e:
            logger.exception(
                f"aggregate_llm_usage_series_task granularity={gran} failed: {e}"
            )
            TaskTracker.update_task_status(
                task_id,
                TaskStatus.FAILURE,
                error=str(e),
                traceback="".join(
                    tb.format_exception(type(e), e, e.__traceback__)
                ),
            )
            raise
    if granularity not in (
        SERIES_GRANULARITY_HOUR,
        SERIES_GRANULARITY_DAY,
        SERIES_GRANULARITY_MONTH,
    ):
        logger.warning(
            f"aggregate_llm_usage_series_task: invalid granularity={granularity}"
        )
        out = {"upserted": 0, "error": "invalid_granularity"}
        TaskTracker.update_task_status(
            task_id, TaskStatus.SUCCESS, result=out
        )
        return out
    try:
        n = _run_one_granularity(granularity, start_date, end_date)
        out = {"upserted": n, "granularity": granularity}
        TaskTracker.update_task_status(
            task_id, TaskStatus.SUCCESS, result=out
        )
        logger.info(
            f"Finished aggregate_llm_usage_series_task granularity={granularity} "
            f"upserted={n}"
        )
        return out
    except Exception as e:
        logger.exception(f"aggregate_llm_usage_series_task failed: {e}")
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(e),
            traceback="".join(
                tb.format_exception(type(e), e, e.__traceback__)
            ),
        )
        raise
