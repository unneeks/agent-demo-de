document.addEventListener('click', function(e) {
  var a = e.target.closest('a');
  if (!a) return;
  var h = a.getAttribute('href');
  if (!h || h.charAt(0) !== '/') return;
  var loc = window.location.pathname;
  var parts = loc.split('/');
  if (parts.length >= 3 && parts[1] === String.fromCharCode(97,112,112)) {
    var base = '/' + parts[1] + '/' + parts[2];
    if (h.indexOf(base) !== 0) {
      e.preventDefault();
      window.location.href = base + h;
    }
  }
});
