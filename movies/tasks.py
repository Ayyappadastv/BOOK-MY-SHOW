import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger('email_tasks')


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name='movies.tasks.send_booking_email')
def send_booking_confirmation_email(self, booking_id):
    """Send HTML booking confirmation email asynchronously with retry logic."""
    try:
        from .models import Booking
        booking = Booking.objects.select_related(
            'user', 'show__movie', 'show__screen__theater'
        ).prefetch_related('seats').get(pk=booking_id)

        ctx = {
            'booking': booking,
            'user': booking.user,
            'show': booking.show,
            'movie': booking.show.movie,
            'theater': booking.show.screen.theater,
            'seats': list(booking.seats.all()),
            'payment': getattr(booking, 'payment', None),
        }
        html_message = render_to_string('emails/booking_confirmation.html', ctx)
        plain_message = (
            f"Booking Confirmed!\n\n"
            f"Movie: {booking.show.movie.title}\n"
            f"Date: {booking.show.start_time}\n"
            f"Theater: {booking.show.screen.theater.name}\n"
            f"Seats: {', '.join([str(s) for s in ctx['seats']])}\n"
            f"Total: ₹{booking.total_amount}\n"
        )
        send_mail(
            subject=f'🎬 Booking Confirmed – {booking.show.movie.title}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f'Confirmation email sent for Booking #{booking_id}')
    except Exception as exc:
        logger.error(f'Email failed for Booking #{booking_id}: {exc}')
        raise self.retry(exc=exc)


@shared_task(name='movies.tasks.release_expired_reservations')
def release_expired_reservations():
    """Periodic task (every 60s via Celery Beat) to expire timed-out seat reservations."""
    from .models import SeatReservation
    now = timezone.now()
    expired_qs = SeatReservation.objects.filter(
        status=SeatReservation.STATUS_RESERVED,
        expires_at__lte=now
    )
    count = expired_qs.count()
    expired_qs.update(status=SeatReservation.STATUS_EXPIRED)
    if count:
        logger.warning(f'Released {count} expired seat reservations.')
    return count
