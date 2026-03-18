from django.urls import path
from . import views

app_name = 'movies'

urlpatterns = [
    path('', views.home, name='home'),
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),
    path('show/<int:show_id>/seats/', views.seat_selection, name='seat_selection'),
    path('show/<int:show_id>/reserve/', views.reserve_seats, name='reserve_seats'),
    path('show/<int:show_id>/order/', views.create_order, name='create_order'),
    path('payment/verify/', views.verify_payment, name='verify_payment'),
    path('payment/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('booking/<int:booking_id>/success/', views.booking_success, name='booking_success'),
]
