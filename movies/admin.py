from django.contrib import admin
from .models import Genre, Language, Movie, Theater, Screen, Seat, Show, SeatReservation, Booking, Payment


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    list_display = ['name', 'slug']


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['title', 'release_date', 'rating', 'is_active']
    list_filter = ['genres', 'languages', 'rating', 'is_active']
    search_fields = ['title']
    filter_horizontal = ['genres', 'languages']


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'city']
    list_filter = ['city']
    search_fields = ['name', 'city']


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ['name', 'theater', 'capacity']
    inlines = [SeatInline]


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):
    list_display = ['movie', 'screen', 'start_time', 'price_normal', 'is_active']
    list_filter = ['is_active', 'start_time']
    search_fields = ['movie__title']


@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ['seat', 'show', 'user', 'status', 'reserved_at', 'expires_at']
    list_filter = ['status']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'show', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'idempotency_key']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'booking', 'razorpay_order_id', 'amount', 'status', 'created_at']
    list_filter = ['status']
