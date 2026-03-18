from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date
from movies.models import Genre, Language, Movie, Theater, Screen, Seat, Show
from accounts.models import User
import random


class Command(BaseCommand):
    help = 'Seed the database with demo movies, theaters, genres, and shows'

    GENRES = ['Action', 'Drama', 'Comedy', 'Thriller', 'Horror', 'Romance', 'Sci-Fi', 'Animation', 'Adventure', 'Biography']
    LANGUAGES = ['English', 'Hindi', 'Malayalam', 'Tamil', 'Telugu', 'Kannada']
    MOVIES = [
        {'title': 'The Final Frontier', 'description': 'A crew of astronauts ventures beyond known space in search of a new home for humanity.', 'duration': 148, 'rating': 'UA', 'trailer': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'genres': ['Sci-Fi', 'Adventure'], 'langs': ['English', 'Hindi']},
        {'title': 'Neon Shadows', 'description': 'A cyberpunk detective uncovers a conspiracy that goes all the way to the top of a megacorporation.', 'duration': 132, 'rating': 'UA', 'trailer': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'genres': ['Thriller', 'Action'], 'langs': ['English']},
        {'title': 'Kaleidoscope Love', 'description': 'A heartwarming story of two strangers who meet on a cross-country train journey.', 'duration': 118, 'rating': 'U', 'trailer': '', 'genres': ['Romance', 'Drama'], 'langs': ['Hindi', 'English']},
        {'title': 'The Last Comedian', 'description': 'A darkly comic tale of a stand-up comedian fighting his inner demons on the night of the biggest show of his life.', 'duration': 105, 'rating': 'A', 'trailer': '', 'genres': ['Comedy', 'Drama'], 'langs': ['English']},
        {'title': 'Phantom Protocol', 'description': 'An elite black-ops unit must stop a rogue AI from triggering a global nuclear war.', 'duration': 155, 'rating': 'UA', 'trailer': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'genres': ['Action', 'Thriller'], 'langs': ['English', 'Tamil']},
        {'title': 'Whispers in the Dark', 'description': 'A family moves into a century-old mansion, only to uncover its terrifying history.', 'duration': 112, 'rating': 'A', 'trailer': '', 'genres': ['Horror'], 'langs': ['English', 'Hindi']},
        {'title': 'Dragon Tales: Reborn', 'description': 'An animated epic where a young girl discovers she can communicate with dragons.', 'duration': 98, 'rating': 'U', 'trailer': '', 'genres': ['Animation', 'Adventure'], 'langs': ['English', 'Hindi', 'Tamil', 'Telugu']},
        {'title': 'The Untold Story', 'description': 'A biographical drama following the life of a revolutionary scientist who changed the world.', 'duration': 162, 'rating': 'UA', 'trailer': '', 'genres': ['Biography', 'Drama'], 'langs': ['English']},
        {'title': 'Red Horizon', 'description': 'A war epic set in the deserts of a fictional nation, following two soldiers on opposite sides.', 'duration': 175, 'rating': 'A', 'trailer': '', 'genres': ['Action', 'Drama'], 'langs': ['Hindi', 'English']},
        {'title': 'Starfall', 'description': 'When a meteor shower brings alien seeds to Earth, one botanist races to prevent the invasion.', 'duration': 130, 'rating': 'UA', 'trailer': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'genres': ['Sci-Fi', 'Action'], 'langs': ['English', 'Malayalam']},
        {'title': 'Comedy Central Chaos', 'description': 'Three roommates accidentally get involved in an international espionage plot.', 'duration': 108, 'rating': 'UA', 'trailer': '', 'genres': ['Comedy', 'Adventure'], 'langs': ['Hindi']},
        {'title': 'Beyond the Horizon', 'description': 'An emotional journey of a father and son sailing around the world together.', 'duration': 125, 'rating': 'U', 'trailer': '', 'genres': ['Adventure', 'Drama'], 'langs': ['English', 'Malayalam']},
    ]
    THEATERS = [
        {'name': 'PVR Cinemas', 'city': 'Mumbai', 'address': 'Phoenix Mall, Lower Parel'},
        {'name': 'INOX Megaplex', 'city': 'Bangalore', 'address': 'Forum Mall, Koramangala'},
        {'name': 'Cinepolis', 'city': 'Delhi', 'address': 'DLF Mall of India, Noida'},
        {'name': 'SPI Cinemas', 'city': 'Chennai', 'address': 'Express Avenue, Royapettah'},
        {'name': 'Carnival Cinemas', 'city': 'Kochi', 'address': 'Lulu Mall, Edappally'},
    ]

    def handle(self, *args, **kwargs):
        self.stdout.write('🌱 Seeding database...')

        # Genres
        genre_objs = {}
        for g in self.GENRES:
            obj, _ = Genre.objects.get_or_create(name=g, defaults={'slug': g.lower().replace(' ', '-').replace('/', '-')})
            genre_objs[g] = obj

        # Languages
        lang_objs = {}
        for l in self.LANGUAGES:
            obj, _ = Language.objects.get_or_create(name=l)
            lang_objs[l] = obj

        # Movies
        movie_objs = []
        for i, m in enumerate(self.MOVIES):
            today = date.today()
            release = today - timedelta(days=random.randint(1, 180))
            movie, _ = Movie.objects.get_or_create(
                title=m['title'],
                defaults={
                    'description': m['description'],
                    'duration_minutes': m['duration'],
                    'rating': m['rating'],
                    'trailer_url': m['trailer'],
                    'release_date': release,
                    'is_active': True,
                }
            )
            movie.genres.set([genre_objs[g] for g in m['genres']])
            movie.languages.set([lang_objs[l] for l in m['langs']])
            movie_objs.append(movie)
            self.stdout.write(f'  ✔ Movie: {movie.title}')

        # Theaters, Screens, Seats, Shows
        now = timezone.now()
        for t in self.THEATERS:
            theater, _ = Theater.objects.get_or_create(name=t['name'], city=t['city'], defaults={'address': t['address']})
            for screen_num in range(1, 4):
                screen, _ = Screen.objects.get_or_create(
                    theater=theater,
                    name=f'Screen {screen_num}',
                    defaults={'capacity': 80}
                )
                # Create seats
                if not screen.seats.exists():
                    for row in 'ABCDEFGH':
                        for num in range(1, 11):
                            seat_type = 'recliner' if row in 'GH' else ('premium' if row in 'EF' else 'normal')
                            Seat.objects.get_or_create(screen=screen, row=row, number=num, defaults={'seat_type': seat_type})

                # Create shows for next 3 days
                movies_sample = random.sample(movie_objs, min(3, len(movie_objs)))
                for movie in movies_sample:
                    for day_offset in range(3):
                        for hour in [10, 14, 18, 21]:
                            show_time = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
                            Show.objects.get_or_create(
                                movie=movie, screen=screen, start_time=show_time,
                                defaults={'price_normal': 150, 'price_premium': 250, 'price_recliner': 400, 'is_active': True}
                            )

            self.stdout.write(f'  ✔ Theater: {theater.name}, {theater.city}')

        # Create superuser (admin)
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@bookmyshow.com',
                password='Admin@BMS2025',
                is_admin_user=True,
            )
            self.stdout.write('  ✔ Admin user created (username: admin, password: Admin@BMS2025)')
        else:
            self.stdout.write('  ℹ Admin user already exists')

        self.stdout.write(self.style.SUCCESS('\n✅ Database seeded successfully!'))
        self.stdout.write('   🔐 Admin: username=admin  password=Admin@BMS2025')
        self.stdout.write('   🌐 Run: python manage.py runserver')
