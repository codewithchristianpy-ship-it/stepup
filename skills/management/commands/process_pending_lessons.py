"""
Daily task: auto-approve or auto-reject pending community lessons.

Rules:
  - Pending lesson with 2+ helpful votes, older than 48 hours → approve
  - Pending lesson with 0 votes, older than 7 days → reject
  - Everything else → stays pending

Run manually:  python manage.py process_pending_lessons
Run on schedule: cron / Render cron job / GitHub Actions
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from skills.models import Lesson
from credits.models import CreditWallet, CreditTransaction


class Command(BaseCommand):
    help = "Auto-approve or auto-reject stale pending lessons."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without changing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        approve_cutoff = now - timedelta(hours=48)
        reject_cutoff = now - timedelta(days=7)

        pending = Lesson.objects.filter(status='pending', is_official=False)

        approved_count = 0
        rejected_count = 0

        # === AUTO-APPROVE ===
        to_approve = pending.filter(
            helpful_votes__gte=2,
            created_at__lte=approve_cutoff,
        )

        for lesson in to_approve:
            if dry_run:
                self.stdout.write(f"[DRY] Would approve: {lesson.title} ({lesson.helpful_votes} votes)")
                continue

            lesson.status = 'published'
            lesson.review_reason = f"Auto-approved after 48h with {lesson.helpful_votes} votes."
            lesson.save()

            # Award credit to author
            if lesson.author:
                try:
                    wallet = lesson.author.wallet
                    wallet.add_credits(
                        amount=1,
                        description=f"Auto-approved lesson: {lesson.title}",
                        transaction_type='earned_teaching',
                    )
                except Exception:
                    pass

                # Update trust
                profile = lesson.author.profile
                profile.approved_lesson_count += 1
                profile.update_trust_status()

            approved_count += 1

        # === AUTO-REJECT ===
        to_reject = pending.filter(
            helpful_votes=0,
            created_at__lte=reject_cutoff,
        )

        for lesson in to_reject:
            if dry_run:
                self.stdout.write(f"[DRY] Would reject: {lesson.title}")
                continue

            lesson.status = 'rejected'
            lesson.review_reason = "Auto-rejected: no helpful votes after 7 days."
            lesson.save()

            # Update author's reject count
            if lesson.author:
                profile = lesson.author.profile
                profile.rejected_lesson_count += 1
                profile.update_trust_status()

            rejected_count += 1

        # === REPORT ===
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN] Would approve {to_approve.count()}, reject {to_reject.count()}."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Auto-approved {approved_count}, auto-rejected {rejected_count}."
            ))
            self.stdout.write(f"Remaining pending: {Lesson.objects.filter(status='pending').count()}")