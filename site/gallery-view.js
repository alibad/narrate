export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

export function filmCard(f) {
  const e = escapeHtml;
  return `<article class="film-card"><div class="film-cover" style="background:${e(f.color || '#dfdfd3')}"><img src="${e(f.poster)}" alt="Actual ${e(f.language)} screen for ${e(f.article)}" width="1920" height="1080" loading="lazy"><div class="cover-tint"></div><a class="cover-play" href="/films/${e(f.id)}/" data-film="${e(f.id)}" aria-label="Watch ${e(f.title)} in ${e(f.language)}"><span class="play-symbol" aria-hidden="true">▶</span></a><span class="draft-pill">REVIEW CUT</span><div class="cover-labels"><span lang="${e(f.id)}" dir="${f.rtl ? 'rtl' : 'ltr'}">${e(f.native)}</span><span>${Math.round(f.duration)} sec</span></div></div><div class="film-topline"><span>${e(f.language.toUpperCase())}</span><span>${e(f.category)}</span></div><h3 lang="${e(f.id)}" dir="${f.rtl ? 'rtl' : 'ltr'}"><a href="/films/${e(f.id)}/">${e(f.nativeTitle || f.title)}</a></h3><p>${e(f.subtitle)}</p></article>`;
}
