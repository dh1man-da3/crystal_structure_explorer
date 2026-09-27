"use strict";

// Informational pages use the locally vendored KaTeX without loading the viewer.
// The original text remains readable if math rendering is unavailable.
if (window.katex?.render) {
  for (const element of document.querySelectorAll("[data-tex]")) {
    window.katex.render(element.dataset.tex, element, {
      throwOnError: false,
      trust: false,
    });
  }
}
