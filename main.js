// Change navbar background on scroll
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
});

// Add scroll reveal animations
const sections = document.querySelectorAll('section');

const observerOptions = {
    threshold: 0.15,
    rootMargin: '0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('section-visible');
        } else {
            // Optional: remove class when section is out of view for repeat animations
            // entry.target.classList.remove('section-visible');
        }
    });
}, observerOptions);

sections.forEach(section => {
    if (section.id !== 'home') {
        section.classList.add('section-hidden');
        observer.observe(section);
    }
});

document.addEventListener('DOMContentLoaded', () => {
    // Smooth scroll for all navigation links
    document.querySelectorAll('.scroll-link, .nav-links a').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const targetId = link.getAttribute('href');
            const targetSection = document.querySelector(targetId);
            
            targetSection.scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
});
