import re
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.models import User


def validate_youtube_url(value):
    """Validate that the URL is a legitimate YouTube URL."""
    youtube_pattern = re.compile(
        r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}(&.*)?$'
    )
    if value and not youtube_pattern.match(value):
        raise ValidationError('Enter a valid YouTube URL (e.g. https://www.youtube.com/watch?v=VIDEO_ID).')


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return self.name


class Movie(models.Model):
    RATING_CHOICES = [
        ('U', 'U – Universal'),
        ('UA', 'UA – Parental Guidance'),
        ('A', 'A – Adults Only'),
    ]
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    poster = models.ImageField(upload_to='posters/', blank=True, null=True)
    trailer_url = models.URLField(max_length=300, blank=True, validators=[validate_youtube_url])
    duration_minutes = models.PositiveIntegerField(default=120)
    release_date = models.DateField(db_index=True)
    rating = models.CharField(max_length=5, choices=RATING_CHOICES, default='UA')
    genres = models.ManyToManyField(Genre, related_name='movies', blank=True)
    languages = models.ManyToManyField(Language, related_name='movies', blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'release_date']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    def get_embed_url(self):
        """Convert YouTube watch URL to embeddable URL."""
        if not self.trailer_url:
            return None
        video_id_match = re.search(r'(?:v=|youtu\.be/)([\w-]{11})', self.trailer_url)
        if video_id_match:
            return f"https://www.youtube-nocookie.com/embed/{video_id_match.group(1)}?rel=0&modestbranding=1"
        return None


class Theater(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    city = models.CharField(max_length=100, db_index=True)
    address = models.TextField()

    def __str__(self):
        return f"{self.name} – {self.city}"


class Screen(models.Model):
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='screens')
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"{self.theater.name} – {self.name}"


class Seat(models.Model):
    SEAT_TYPE_CHOICES = [
        ('normal', 'Normal'),
        ('premium', 'Premium'),
        ('recliner', 'Recliner'),
    ]
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='seats')
    row = models.CharField(max_length=5)
    number = models.PositiveIntegerField()
    seat_type = models.CharField(max_length=10, choices=SEAT_TYPE_CHOICES, default='normal')

    class Meta:
        unique_together = ('screen', 'row', 'number')

    def __str__(self):
        return f"{self.row}{self.number} ({self.seat_type})"


class Show(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='shows')
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='shows')
    start_time = models.DateTimeField(db_index=True)
    price_normal = models.DecimalField(max_digits=8, decimal_places=2, default=150)
    price_premium = models.DecimalField(max_digits=8, decimal_places=2, default=250)
    price_recliner = models.DecimalField(max_digits=8, decimal_places=2, default=400)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['movie', 'start_time']),
            models.Index(fields=['screen', 'start_time']),
        ]

    def __str__(self):
        return f"{self.movie.title} @ {self.screen} – {self.start_time}"

    def get_price_for_seat(self, seat):
        prices = {'normal': self.price_normal, 'premium': self.price_premium, 'recliner': self.price_recliner}
        return prices.get(seat.seat_type, self.price_normal)


class SeatReservation(models.Model):
    STATUS_RESERVED = 'reserved'
    STATUS_BOOKED = 'booked'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_RESERVED, 'Reserved'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_EXPIRED, 'Expired'),
    ]
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='reservations')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='reservations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_RESERVED, db_index=True)
    reserved_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['show', 'seat', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]

    def __str__(self):
        return f"{self.seat} for {self.show} – {self.status}"

    def is_expired(self):
        return timezone.now() > self.expires_at


class Booking(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='bookings')
    seats = models.ManyToManyField(Seat, related_name='bookings')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    idempotency_key = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['show', 'status']),
        ]

    def __str__(self):
        return f"Booking #{self.pk} – {self.user} – {self.status}"


class Payment(models.Model):
    STATUS_CREATED = 'created'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (STATUS_CREATED, 'Created'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_CREATED, db_index=True)
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for Booking #{self.booking_id} – {self.status}"
