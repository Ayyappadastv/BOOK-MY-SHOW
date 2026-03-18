import uuid
import hashlib
import hmac
import json
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Count, Q, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import razorpay

from .models import (
    Movie, Genre, Language, Show, Seat, SeatReservation, Booking, Payment
)
from .tasks import send_booking_confirmation_email

logger = logging.getLogger('movies')


# ─── Home / Movie Listing with Filters ────────────────────────────────────────
def home(request):
    """
    Movie listing with multi-select genre/language filters.
    Server-side filtered with optimized queries + dynamic filter counts.
    """
    genres = Genre.objects.all().order_by('name')
    languages = Language.objects.all().order_by('name')

    selected_genres = request.GET.getlist('genre')
    selected_languages = request.GET.getlist('language')
    sort_by = request.GET.get('sort', '-release_date')
    search_q = request.GET.get('q', '').strip()

    VALID_SORTS = ['-release_date', 'release_date', 'title', '-title']
    if sort_by not in VALID_SORTS:
        sort_by = '-release_date'

    # Base queryset – active movies with prefetch (avoids N+1)
    movies_qs = Movie.objects.filter(is_active=True).prefetch_related('genres', 'languages')

    if search_q:
        movies_qs = movies_qs.filter(title__icontains=search_q)

    if selected_genres:
        movies_qs = movies_qs.filter(genres__slug__in=selected_genres).distinct()

    if selected_languages:
        movies_qs = movies_qs.filter(languages__name__in=selected_languages).distinct()

    movies_qs = movies_qs.order_by(sort_by)

    # Dynamic filter counts – count movies per genre/language AFTER applying other filters
    # After genre filter: apply language filter first then count genres
    filtered_for_genre_counts = Movie.objects.filter(is_active=True)
    if search_q:
        filtered_for_genre_counts = filtered_for_genre_counts.filter(title__icontains=search_q)
    if selected_languages:
        filtered_for_genre_counts = filtered_for_genre_counts.filter(
            languages__name__in=selected_languages
        ).distinct()

    genre_counts = (
        Genre.objects.filter(movies__in=filtered_for_genre_counts)
        .annotate(movie_count=Count('movies', distinct=True))
        .values('slug', 'movie_count')
    )
    genre_count_map = {g['slug']: g['movie_count'] for g in genre_counts}

    filtered_for_lang_counts = Movie.objects.filter(is_active=True)
    if search_q:
        filtered_for_lang_counts = filtered_for_lang_counts.filter(title__icontains=search_q)
    if selected_genres:
        filtered_for_lang_counts = filtered_for_lang_counts.filter(
            genres__slug__in=selected_genres
        ).distinct()

    lang_counts = (
        Language.objects.filter(movies__in=filtered_for_lang_counts)
        .annotate(movie_count=Count('movies', distinct=True))
        .values('name', 'movie_count')
    )
    lang_count_map = {l['name']: l['movie_count'] for l in lang_counts}

    # Pagination
    paginator = Paginator(movies_qs, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'genres': genres,
        'languages': languages,
        'selected_genres': selected_genres,
        'selected_languages': selected_languages,
        'sort_by': sort_by,
        'search_q': search_q,
        'genre_count_map': genre_count_map,
        'lang_count_map': lang_count_map,
        'total_count': movies_qs.count(),
    }
    return render(request, 'movies/home.html', context)


# ─── Movie Detail ──────────────────────────────────────────────────────────────
def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk, is_active=True)
    shows = Show.objects.filter(
        movie=movie,
        start_time__gte=timezone.now(),
        is_active=True
    ).select_related('screen__theater').order_by('start_time')
    embed_url = movie.get_embed_url()
    return render(request, 'movies/movie_detail.html', {
        'movie': movie,
        'shows': shows,
        'embed_url': embed_url,
    })


# ─── Seat Selection ────────────────────────────────────────────────────────────
@login_required
def seat_selection(request, show_id):
    show = get_object_or_404(Show, pk=show_id, is_active=True)
    seats = Seat.objects.filter(screen=show.screen).order_by('row', 'number')

    # Get reserved/booked seat IDs for this show
    unavailable_seat_ids = set(
        SeatReservation.objects.filter(
            show=show,
            status__in=[SeatReservation.STATUS_RESERVED, SeatReservation.STATUS_BOOKED]
        ).values_list('seat_id', flat=True)
    )

    seats_by_row = {}
    for seat in seats:
        row_list = seats_by_row.setdefault(seat.row, [])
        row_list.append({
            'id': seat.id,
            'number': seat.number,
            'type': seat.seat_type,
            'price': float(show.get_price_for_seat(seat)),
            'unavailable': seat.id in unavailable_seat_ids,
        })

    return render(request, 'movies/seat_selection.html', {
        'show': show,
        'seats_by_row': seats_by_row,
    })


# ─── Reserve Seats (Concurrency-Safe) ─────────────────────────────────────────
@login_required
@require_POST
def reserve_seats(request, show_id):
    """
    Atomically reserve seats using select_for_update(nowait=True).
    Seats are locked for 2 minutes. Race conditions are prevented at DB level.
    """
    show = get_object_or_404(Show, pk=show_id, is_active=True)
    seat_ids = request.POST.getlist('seat_ids[]')

    if not seat_ids:
        return JsonResponse({'success': False, 'error': 'No seats selected.'}, status=400)
    if len(seat_ids) > 10:
        return JsonResponse({'success': False, 'error': 'Maximum 10 seats per booking.'}, status=400)

    expires_at = timezone.now() + timedelta(minutes=2)

    try:
        with transaction.atomic():
            # Lock rows for selected seats using SELECT FOR UPDATE NOWAIT
            seats = list(
                Seat.objects.select_for_update(nowait=True)
                .filter(id__in=seat_ids, screen=show.screen)
            )
            if len(seats) != len(seat_ids):
                return JsonResponse({'success': False, 'error': 'Invalid seat selection.'}, status=400)

            # Check no active reservation exists for these seats
            conflict = SeatReservation.objects.filter(
                show=show,
                seat__in=seats,
                status__in=[SeatReservation.STATUS_RESERVED, SeatReservation.STATUS_BOOKED]
            ).exists()
            if conflict:
                return JsonResponse({
                    'success': False,
                    'error': 'One or more seats were just taken. Please choose again.'
                }, status=409)

            # Expire any old reservations by this user for this show
            SeatReservation.objects.filter(
                show=show, user=request.user, status=SeatReservation.STATUS_RESERVED
            ).update(status=SeatReservation.STATUS_EXPIRED)

            # Create new reservations
            reservations = [
                SeatReservation(
                    show=show, seat=seat,
                    user=request.user, expires_at=expires_at
                ) for seat in seats
            ]
            SeatReservation.objects.bulk_create(reservations)

            # Calculate total
            total = sum(float(show.get_price_for_seat(s)) for s in seats)

        return JsonResponse({
            'success': True,
            'expires_at': expires_at.isoformat(),
            'total': total,
            'seat_ids': [s.id for s in seats],
        })

    except Exception as e:
        logger.error(f'Seat reservation error: {e}')
        return JsonResponse({
            'success': False,
            'error': 'Seats are currently being held. Please try again.'
        }, status=409)


# ─── Create Razorpay Order ─────────────────────────────────────────────────────
@login_required
@require_POST
def create_order(request, show_id):
    show = get_object_or_404(Show, pk=show_id, is_active=True)
    seat_ids = request.POST.getlist('seat_ids[]')

    if not seat_ids:
        messages.error(request, 'Please select seats first.')
        return redirect('movies:seat_selection', show_id=show_id)

    # Verify reservations still active
    reservations = SeatReservation.objects.filter(
        show=show, seat_id__in=seat_ids,
        user=request.user, status=SeatReservation.STATUS_RESERVED
    )
    if reservations.count() != len(seat_ids):
        messages.error(request, 'Your seat reservation has expired. Please select again.')
        return redirect('movies:seat_selection', show_id=show_id)

    seats = Seat.objects.filter(id__in=seat_ids)
    total = sum(show.get_price_for_seat(s) for s in seats)
    idempotency_key = str(uuid.uuid4())

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    order_data = {
        'amount': int(total * 100),  # Razorpay uses paise
        'currency': 'INR',
        'receipt': idempotency_key[:40],
        'notes': {'booking_user': request.user.username, 'show_id': str(show_id)},
    }
    try:
        razorpay_order = client.order.create(data=order_data)
    except Exception as e:
        logger.error(f'Razorpay order creation error: {e}')
        messages.error(request, 'Payment service unavailable. Please try again.')
        return redirect('movies:seat_selection', show_id=show_id)

    # Create pending Booking + Payment
    with transaction.atomic():
        booking = Booking.objects.create(
            user=request.user,
            show=show,
            total_amount=total,
            idempotency_key=idempotency_key,
            status=Booking.STATUS_PENDING,
        )
        booking.seats.set(seats)
        Payment.objects.create(
            booking=booking,
            razorpay_order_id=razorpay_order['id'],
            amount=total,
            status=Payment.STATUS_CREATED,
        )

    return render(request, 'movies/checkout.html', {
        'booking': booking,
        'show': show,
        'seats': seats,
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'total': total,
    })


# ─── Payment Verification ──────────────────────────────────────────────────────
@login_required
@require_POST
def verify_payment(request):
    """Server-side Razorpay HMAC signature verification."""
    payment_id = request.POST.get('razorpay_payment_id', '')
    order_id = request.POST.get('razorpay_order_id', '')
    signature = request.POST.get('razorpay_signature', '')

    # HMAC-SHA256 verification
    msg = f"{order_id}|{payment_id}"
    expected_sig = hmac.new(
        bytes(settings.RAZORPAY_KEY_SECRET, 'utf-8'),
        bytes(msg, 'utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        logger.error(f'Invalid Razorpay signature for order {order_id}')
        messages.error(request, 'Payment verification failed. Please contact support.')
        return redirect('movies:home')

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(razorpay_order_id=order_id)
            if payment.status == Payment.STATUS_PAID:
                # Idempotent: already processed
                return redirect('movies:booking_success', booking_id=payment.booking_id)

            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.status = Payment.STATUS_PAID
            payment.save()

            booking = payment.booking
            booking.status = Booking.STATUS_CONFIRMED
            booking.save()

            # Mark seats as BOOKED
            SeatReservation.objects.filter(
                show=booking.show, seat__in=booking.seats.all(),
                user=request.user, status=SeatReservation.STATUS_RESERVED
            ).update(status=SeatReservation.STATUS_BOOKED)

        # Send email asynchronously (non-blocking)
        send_booking_confirmation_email.delay(booking.id)

        return redirect('movies:booking_success', booking_id=booking.id)

    except Payment.DoesNotExist:
        messages.error(request, 'Booking not found.')
        return redirect('movies:home')
    except Exception as e:
        logger.error(f'Payment verification error: {e}')
        messages.error(request, 'An error occurred. Please contact support.')
        return redirect('movies:home')


# ─── Razorpay Webhook ─────────────────────────────────────────────────────────
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Handles Razorpay webhooks. Validates signature to prevent replay attacks.
    Uses idempotency via Payment status to avoid double processing.
    """
    webhook_secret = settings.RAZORPAY_KEY_SECRET
    received_sig = request.headers.get('X-Razorpay-Signature', '')
    payload = request.body

    expected_sig = hmac.new(
        bytes(webhook_secret, 'utf-8'), payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, received_sig):
        logger.error('Webhook signature mismatch')
        return HttpResponse(status=400)

    try:
        data = json.loads(payload)
        event = data.get('event', '')

        if event == 'payment.captured':
            order_id = data['payload']['payment']['entity']['order_id']
            payment_id = data['payload']['payment']['entity']['id']
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(razorpay_order_id=order_id)
                if payment.status != Payment.STATUS_PAID:
                    payment.razorpay_payment_id = payment_id
                    payment.status = Payment.STATUS_PAID
                    payment.webhook_received_at = timezone.now()
                    payment.save()
                    payment.booking.status = Booking.STATUS_CONFIRMED
                    payment.booking.save()

        elif event == 'payment.failed':
            order_id = data['payload']['payment']['entity']['order_id']
            with transaction.atomic():
                Payment.objects.filter(
                    razorpay_order_id=order_id,
                    status=Payment.STATUS_CREATED
                ).update(status=Payment.STATUS_FAILED)

    except Exception as e:
        logger.error(f'Webhook processing error: {e}')
        return HttpResponse(status=500)

    return HttpResponse(status=200)


# ─── Booking Success ───────────────────────────────────────────────────────────
@login_required
def booking_success(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('show__movie', 'show__screen__theater')
        .prefetch_related('seats'),
        pk=booking_id, user=request.user
    )
    return render(request, 'movies/booking_success.html', {'booking': booking})
