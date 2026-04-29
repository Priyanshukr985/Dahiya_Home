/* ===== NAVBAR SCROLL ===== */
const navbar = document.getElementById('navbar');
const navLinks = document.getElementById('navLinks');
const hamburger = document.getElementById('hamburger');

window.addEventListener('scroll', () => {
  if (window.scrollY > 60) {
    navbar.classList.add('scrolled');
  } else {
    navbar.classList.remove('scrolled');
  }
  // scroll top visibility
  const scrollTop = document.getElementById('scrollTop');
  if (window.scrollY > 400) {
    scrollTop.classList.add('visible');
  } else {
    scrollTop.classList.remove('visible');
  }
  // active nav link highlight
  updateActiveNav();
});

/* ===== HAMBURGER MENU ===== */
hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('open');
  navLinks.classList.toggle('open');
  document.body.classList.toggle('menu-open', navLinks.classList.contains('open'));
});

// Close menu when a link is clicked
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', () => {
    hamburger.classList.remove('open');
    navLinks.classList.remove('open');
    document.body.classList.remove('menu-open');
  });
});

/* ===== ACTIVE NAV HIGHLIGHT ===== */
function updateActiveNav() {
  const sections = document.querySelectorAll('section[id]');
  let current = '';
  sections.forEach(s => {
    const top = s.offsetTop - 100;
    if (window.scrollY >= top) current = s.getAttribute('id');
  });
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href') === '#' + current) link.classList.add('active');
  });
}

/* ===== SCROLL TO TOP ===== */
document.getElementById('scrollTop').addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

/* ===== FLOOR PLAN TABS ===== */
document.querySelectorAll('.plan-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const plan = tab.dataset.plan;
    document.querySelectorAll('.plan-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.plan-content').forEach(c => c.classList.add('hidden'));
    tab.classList.add('active');
    document.getElementById('plan-' + plan).classList.remove('hidden');
  });
});

/* ===== FORM VALIDATION & SUBMIT ===== */
const form = document.getElementById('enquiryForm');
const submitBtn = document.getElementById('submitBtn');
const spinner = document.getElementById('spinner');
const formSuccess = document.getElementById('formSuccess');
const formStatus = document.getElementById('formStatus');
const btnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;

function showError(fieldId, msg) {
  const el = document.getElementById(fieldId + '-error');
  const input = document.getElementById(fieldId);
  if (el) el.textContent = msg;
  if (input) input.classList.add('error');
}
function clearError(fieldId) {
  const el = document.getElementById(fieldId + '-error');
  const input = document.getElementById(fieldId);
  if (el) el.textContent = '';
  if (input) input.classList.remove('error');
}
function setFormStatus(message, type = 'error') {
  if (!formStatus) return;
  formStatus.textContent = message;
  formStatus.classList.remove('hidden', 'is-error', 'is-success');
  formStatus.classList.add(type === 'success' ? 'is-success' : 'is-error');
}
function clearFormStatus() {
  if (!formStatus) return;
  formStatus.textContent = '';
  formStatus.classList.add('hidden');
  formStatus.classList.remove('is-error', 'is-success');
}
function setSubmittingState(isSubmitting) {
  if (btnText) btnText.textContent = isSubmitting ? 'Submitting...' : 'Schedule a Site Visit';
  if (spinner) spinner.classList.toggle('hidden', !isSubmitting);
  if (submitBtn) submitBtn.disabled = isSubmitting;
}
function validateForm() {
  let valid = true;
  const name = document.getElementById('name');
  const phone = document.getElementById('phone');
  clearError('name'); clearError('phone'); clearFormStatus();
  if (!name || !name.value.trim()) {
    showError('name', 'Full name is required.'); valid = false;
  }
  if (!phone || !phone.value.trim()) {
    showError('phone', 'Phone number is required.'); valid = false;
  } else if (!/^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/.test(phone.value.replace(/\s/g, ''))) {
    showError('phone', 'Please enter a valid phone number.'); valid = false;
  }
  return valid;
}

if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    const payload = {
      full_name: document.getElementById('name')?.value.trim() || '',
      phone_number: document.getElementById('phone')?.value.trim() || '',
      email_address: document.getElementById('email')?.value.trim() || '',
      apartment_interest: document.getElementById('config')?.value || '',
      preferred_visit_date: document.getElementById('visit-date')?.value || '',
      message: document.getElementById('message')?.value.trim() || ''
    };

    setSubmittingState(true);

    try {
      const response = await fetch('/api/enquiries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        const fieldErrors = result.errors || {};
        if (fieldErrors.full_name) showError('name', fieldErrors.full_name);
        if (fieldErrors.phone_number) showError('phone', fieldErrors.phone_number);

        const fallbackMessage = result.error || fieldErrors.email_address || fieldErrors.apartment_interest
          || fieldErrors.preferred_visit_date || fieldErrors.message
          || 'We could not submit your enquiry. Please try again.';

        setFormStatus(fallbackMessage, 'error');
        return;
      }

      form.classList.add('hidden');
      formSuccess.classList.remove('hidden');
      setFormStatus(result.message || 'Enquiry submitted successfully.', 'success');
      form.reset();
    } catch (error) {
      setFormStatus('Server se connect nahi ho paaya. Flask backend chalu karke phir try karein.', 'error');
    } finally {
      setSubmittingState(false);
    }
  });

  // Live validation
  document.getElementById('name')?.addEventListener('input', () => {
    clearError('name');
    clearFormStatus();
  });
  document.getElementById('phone')?.addEventListener('input', () => {
    clearError('phone');
    clearFormStatus();
  });
}

/* ===== INTERSECTION OBSERVER – ANIMATE ON SCROLL ===== */
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.animationPlayState = 'running';
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.amenity-card').forEach(card => {
  card.style.animationPlayState = 'paused';
  observer.observe(card);
});

/* ===== ANIMATE RATING BARS ON SCROLL ===== */
const barObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.querySelectorAll('.bar-inner').forEach(bar => {
        const w = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => { bar.style.width = w; }, 100);
      });
      barObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.3 });

document.querySelectorAll('.rating-summary').forEach(el => barObserver.observe(el));

/* ===== HERO PARTICLES (subtle floating dots) ===== */
const canvas = document.createElement('canvas');
const particlesDiv = document.getElementById('particles');
if (particlesDiv) {
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;opacity:0.35;pointer-events:none;';
  particlesDiv.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  let W = canvas.width = window.innerWidth;
  let H = canvas.height = window.innerHeight;
  const dots = Array.from({length: 55}, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    r: Math.random() * 1.5 + 0.5,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    a: Math.random()
  }));
  function drawParticles() {
    ctx.clearRect(0, 0, W, H);
    dots.forEach(d => {
      d.x += d.vx; d.y += d.vy;
      if (d.x < 0) d.x = W; if (d.x > W) d.x = 0;
      if (d.y < 0) d.y = H; if (d.y > H) d.y = 0;
      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(212,175,55,${d.a * 0.6})`;
      ctx.fill();
    });
    requestAnimationFrame(drawParticles);
  }
  drawParticles();
  window.addEventListener('resize', () => {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  });
}

/* ===== SMOOTH SECTION REVEAL ===== */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.08 });

document.querySelectorAll('.spec-item, .review-card, .location-category, .room-item').forEach(el => {
  el.style.cssText += 'opacity:0;transform:translateY(20px);transition:opacity 0.5s ease,transform 0.5s ease;';
  revealObserver.observe(el);
});

/* ===== LISTING IMAGE SLIDERS ===== */
document.querySelectorAll('[data-listing-slider]').forEach((slider) => {
  const slides = Array.from(slider.querySelectorAll('.listing-slide'));
  if (slides.length < 2) return;

  let activeIndex = slides.findIndex((s) => s.classList.contains('is-active'));
  if (activeIndex < 0) activeIndex = 0;

  const showSlide = (index) => {
    slides.forEach((slide, i) => {
      slide.classList.toggle('is-active', i === index);
    });
    activeIndex = index;
  };

  slider.querySelectorAll('.listing-arrow').forEach((btn) => {
    btn.addEventListener('click', () => {
      const dir = btn.dataset.slideDir;
      const next = dir === 'next'
        ? (activeIndex + 1) % slides.length
        : (activeIndex - 1 + slides.length) % slides.length;
      showSlide(next);
    });
  });

  slider.addEventListener('click', (event) => {
    const target = event.target;
    if (target.closest('.listing-arrow')) return;

    const activeSlide = slides[activeIndex];
    const activeImg = activeSlide?.querySelector('img');
    if (activeImg) {
      openImageLightbox(activeImg.currentSrc || activeImg.src, activeImg.alt);
    }
  });
});

/* ===== IMAGE LIGHTBOX ===== */
const imageLightbox = document.getElementById('imageLightbox');
const lightboxImage = document.getElementById('lightboxImage');
const lightboxClose = document.getElementById('lightboxClose');

function openImageLightbox(src, alt) {
  if (!imageLightbox || !lightboxImage) return;
  lightboxImage.src = src;
  lightboxImage.alt = alt || 'Expanded view';
  imageLightbox.classList.add('open');
  imageLightbox.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeImageLightbox() {
  if (!imageLightbox || !lightboxImage) return;
  imageLightbox.classList.remove('open');
  imageLightbox.setAttribute('aria-hidden', 'true');
  lightboxImage.src = '';
  document.body.classList.remove('menu-open');
}

document.querySelectorAll('.listing-slide img, .gallery-item img, .overview-image-card img').forEach((img) => {
  img.addEventListener('click', () => {
    openImageLightbox(img.currentSrc || img.src, img.alt);
  });
});

lightboxClose?.addEventListener('click', closeImageLightbox);

imageLightbox?.addEventListener('click', (event) => {
  if (event.target === imageLightbox) {
    closeImageLightbox();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && imageLightbox?.classList.contains('open')) {
    closeImageLightbox();
  }
});

