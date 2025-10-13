document.addEventListener('DOMContentLoaded', () => {
  const menuToggle = document.getElementById('mobile-menu-toggle');
  const mobileMenu = document.getElementById('mobile-menu');
  const closeMenu = document.getElementById('close-mobile-menu');
  const backdrop = document.getElementById('mobile-menu-backdrop');

  if (!menuToggle || !mobileMenu || !backdrop) return;

  const openMenu = () => {
    mobileMenu.classList.add('open');
    backdrop.classList.add('show');
    menuToggle.setAttribute('aria-expanded','true');
    mobileMenu.setAttribute('aria-hidden','false');
  };
  const closeMenuFn = () => {
    mobileMenu.classList.remove('open');
    backdrop.classList.remove('show');
    menuToggle.setAttribute('aria-expanded','false');
    mobileMenu.setAttribute('aria-hidden','true');
  };

  menuToggle.addEventListener('click', openMenu);
  if (closeMenu) closeMenu.addEventListener('click', closeMenuFn);
  backdrop.addEventListener('click', closeMenuFn);
  document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') closeMenuFn(); });

  // swipe to open (from left) – optional
  let sx=0, ex=0;
  document.addEventListener('touchstart', e => { if(e.touches?.length===1) sx=e.touches[0].clientX; }, {passive:true});
  document.addEventListener('touchmove', e => { if(e.touches?.length===1) ex=e.touches[0].clientX; }, {passive:true});
  document.addEventListener('touchend', () => {
    if (ex - sx > 60 && window.innerWidth <= 1024) openMenu();
    sx=0; ex=0;
  }, {passive:true});
});
