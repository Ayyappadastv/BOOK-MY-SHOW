from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncHour
from datetime import timedelta


@staff_member_required
def admin_dashboard(request):
    """
    Admin analytics dashboard with DB-level aggregation and Redis caching.
    All queries use GROUP BY at DB level — no full table loads into memory.
    """
    CACHE_KEY = 'admin_dashboard_data'
    data = cache.get(CACHE_KEY)

    if data is None:
        from movies.models import Booking, Payment, Show, SeatReservation

        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        confirmed_bookings = Booking.objects.filter(status='confirmed')

        # ── Revenue ────────────────────────────────────────────────────────
        revenue_daily = (
            confirmed_bookings.filter(created_at__date=today)
            .aggregate(total=Sum('total_amount'))['total'] or 0
        )
        revenue_weekly = (
            confirmed_bookings.filter(created_at__gte=week_ago)
            .aggregate(total=Sum('total_amount'))['total'] or 0
        )
        revenue_monthly = (
            confirmed_bookings.filter(created_at__gte=month_ago)
            .aggregate(total=Sum('total_amount'))['total'] or 0
        )

        # Revenue trend (last 7 days)
        revenue_trend = list(
            confirmed_bookings.filter(created_at__gte=week_ago)
            .annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(total=Sum('total_amount'))
            .order_by('day')
        )

        # ── Top Movies ─────────────────────────────────────────────────────
        top_movies = list(
            confirmed_bookings
            .values('show__movie__title')
            .annotate(booking_count=Count('id'), revenue=Sum('total_amount'))
            .order_by('-booking_count')[:10]
        )

        # ── Busiest Theaters ───────────────────────────────────────────────
        busiest_theaters = list(
            confirmed_bookings
            .values('show__screen__theater__name', 'show__screen__theater__city')
            .annotate(booking_count=Count('id'), revenue=Sum('total_amount'))
            .order_by('-booking_count')[:10]
        )

        # ── Peak Booking Hours ─────────────────────────────────────────────
        peak_hours = list(
            confirmed_bookings.filter(created_at__gte=month_ago)
            .annotate(hour=TruncHour('created_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('hour')
        )

        # ── Cancellation Rate ──────────────────────────────────────────────
        total_bookings = Booking.objects.filter(created_at__gte=month_ago).count()
        cancelled_bookings = Booking.objects.filter(
            created_at__gte=month_ago, status='cancelled'
        ).count()
        cancellation_rate = (
            round((cancelled_bookings / total_bookings * 100), 2)
            if total_bookings else 0
        )

        # ── Total Stats ────────────────────────────────────────────────────
        total_revenue_all_time = (
            Payment.objects.filter(status='paid')
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        total_bookings_confirmed = confirmed_bookings.count()

        data = {
            'revenue_daily': revenue_daily,
            'revenue_weekly': revenue_weekly,
            'revenue_monthly': revenue_monthly,
            'revenue_trend': [
                {'day': str(r['day'].date()), 'total': float(r['total'] or 0)}
                for r in revenue_trend
            ],
            'top_movies': [
                {
                    'title': m['show__movie__title'],
                    'booking_count': m['booking_count'],
                    'revenue': float(m['revenue'] or 0),
                }
                for m in top_movies
            ],
            'busiest_theaters': [
                {
                    'name': t['show__screen__theater__name'],
                    'city': t['show__screen__theater__city'],
                    'booking_count': t['booking_count'],
                    'revenue': float(t['revenue'] or 0),
                }
                for t in busiest_theaters
            ],
            'peak_hours': [
                {'hour': p['hour'].strftime('%H:00'), 'count': p['count']}
                for p in peak_hours
            ],
            'cancellation_rate': cancellation_rate,
            'total_revenue_all_time': float(total_revenue_all_time),
            'total_bookings_confirmed': total_bookings_confirmed,
        }

        cache.set(CACHE_KEY, data, timeout=300)  # Cache for 5 minutes

    return render(request, 'analytics/admin_dashboard.html', {'data': data})
