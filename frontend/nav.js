// Mobile hamburger nav — shared across all pages
(function () {
  const hamburger = document.getElementById('nav-hamburger');
  const navLinks  = document.querySelector('.nav-links');
  if (!hamburger || !navLinks) return;

  function close() {
    hamburger.classList.remove('open');
    navLinks.classList.remove('open');
  }

  hamburger.addEventListener('click', (e) => {
    e.stopPropagation();
    hamburger.classList.toggle('open');
    navLinks.classList.toggle('open');
  });

  // Close when any nav link is tapped
  navLinks.querySelectorAll('a, button').forEach(el => {
    el.addEventListener('click', close);
  });

  // Close when tapping outside the navbar
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.navbar')) close();
  });
})();
