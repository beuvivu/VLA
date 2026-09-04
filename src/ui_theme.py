"""Bộ tiện ích Tailwind tối thiểu, nhúng cục bộ cho trang tĩnh VLA."""

from __future__ import annotations


TAILWIND_LITE_CSS = r"""
*{box-sizing:border-box}
.bg-slate-50{background-color:#f8fafc}.bg-white{background-color:#fff}
.text-slate-800{color:#1e293b}.text-slate-600{color:#475569}.text-slate-400{color:#94a3b8}
.text-indigo-600{color:#4f46e5}.text-blue-600{color:#2563eb}
.border{border-width:1px}.border-slate-200\/60{border-color:rgba(226,232,240,.6)}
.rounded-xl{border-radius:.75rem}.rounded-2xl{border-radius:1rem}
.shadow-sm{box-shadow:0 1px 2px rgba(15,23,42,.06)}.shadow-md{box-shadow:0 4px 12px rgba(15,23,42,.10)}
.flex{display:flex}.grid{display:grid}.flex-wrap{flex-wrap:wrap}.items-center{align-items:center}
.justify-between{justify-content:space-between}.gap-4{gap:1rem}.gap-6{gap:1.5rem}
.p-4{padding:1rem}.p-6{padding:1.5rem}.px-4{padding-left:1rem;padding-right:1rem}
.py-6{padding-top:1.5rem;padding-bottom:1.5rem}.mb-6{margin-bottom:1.5rem}.mt-4{margin-top:1rem}
.mx-auto{margin-left:auto;margin-right:auto}.max-w-6xl{max-width:72rem}.w-full{width:100%}
.transition-all{transition-property:all}.duration-200{transition-duration:.2s}.ease-in-out{transition-timing-function:cubic-bezier(.4,0,.2,1)}
.hover\:shadow-lg:hover{box-shadow:0 10px 25px rgba(15,23,42,.14)}
.hover\:-translate-y-0\.5:hover{transform:translateY(-.125rem)}
.underline{text-decoration-line:underline}.font-bold{font-weight:700}.italic{font-style:italic}
@media (min-width:640px){.sm\:px-6{padding-left:1.5rem;padding-right:1.5rem}}
@media (min-width:768px){.md\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}}
""".strip()


def tailwind_style_tag() -> str:
    """Trả về thẻ style CSP-safe; không gọi CDN bên ngoài."""

    return f'<style id="vla-tailwind-lite">{TAILWIND_LITE_CSS}</style>'
