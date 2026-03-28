import logging
from datetime import datetime, timezone

from celery import Celery, signals

from config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = Celery(
    "contentforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.task_serializer = "json"
app.conf.accept_content = ["json"]
app.conf.result_serializer = "json"
app.conf.timezone = "UTC"
app.conf.imports = ("tasks.generate_content", "tasks.post_content")

# Ack after success so a crashed worker does not lose the message (task may rerun).
app.conf.task_acks_late = True
app.conf.worker_prefetch_multiplier = 1
app.conf.task_reject_on_worker_lost = True
app.conf.broker_connection_retry_on_startup = True

_GENERATION_TASK_NAMES = frozenset(
    {
        "tasks.generate_content.run_full_generation",
        "tasks.generate_content.run_quote_only",
        "tasks.generate_content.run_image_only",
    }
)


def _generation_job_id_from_task_args(args: tuple | list | None) -> int | None:
    if not args:
        return None
    try:
        return int(args[0])
    except (TypeError, ValueError):
        return None


@signals.task_failure.connect(weak=False)
def _mark_generation_job_failed_on_task_failure(
    sender=None,
    exception=None,
    args=None,
    kwargs=None,
    **_extra: object,
) -> None:
    """
    If a generation Celery task dies without finishing (WorkerLostError / SIGKILL, hard time limit,
    or any uncaught error after DB rollback), the job row may still be ``running``.
    This handler marks it ``failed`` when still non-terminal.
    """
    task_name = getattr(sender, "name", None)
    if task_name not in _GENERATION_TASK_NAMES:
        return

    job_id = _generation_job_id_from_task_args(args)
    if job_id is None:
        return

    exc_name = type(exception).__name__ if exception else "Exception"
    msg = str(exception) if exception else "Task failed"
    if exc_name == "WorkerLostError" or "WorkerLostError" in msg:
        msg = (
            "Worker process ended unexpectedly (often out of memory). "
            "Try more Docker RAM, generation retries, or remove the topic style reference. "
            f"Detail: {msg[:1400]}"
        )
    if len(msg) > 2000:
        msg = msg[:1997] + "…"

    from database import SessionLocal
    from models.generation_job import GenerationJob

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job or job.status in ("done", "failed"):
            return
        job.status = "failed"
        job.error_message = msg[:2000]
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Marked generation job %s failed via task_failure (%s)", job_id, exc_name)
    except Exception:
        logger.exception("task_failure handler could not update generation job %s", job_id)
    finally:
        db.close()
