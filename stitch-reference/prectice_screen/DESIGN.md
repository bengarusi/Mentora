---
name: Mentora Core
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#494454'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#7b7486'
  outline-variant: '#cbc3d7'
  surface-tint: '#6d3bd7'
  primary: '#6b38d4'
  on-primary: '#ffffff'
  primary-container: '#8455ef'
  on-primary-container: '#fffbff'
  inverse-primary: '#d0bcff'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#825100'
  on-tertiary: '#ffffff'
  tertiary-container: '#a36700'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e9ddff'
  primary-fixed-dim: '#d0bcff'
  on-primary-fixed: '#23005c'
  on-primary-fixed-variant: '#5516be'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display:
    fontFamily: Quicksand
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Quicksand
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Quicksand
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Quicksand
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Quicksand
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 30px
  body-md:
    fontFamily: Quicksand
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
  label-lg:
    fontFamily: Quicksand
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Quicksand
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 40px
  xl: 64px
  container-max: 1280px
  gutter: 24px
---

## Brand & Style
The design system is engineered for an educational SaaS environment that balances pedagogical authority with a welcoming, student-centric atmosphere. The brand personality is "The Encouraging Mentor": professional enough for administrators and parents to trust, yet vibrant and approachable enough for students in grades 1-7 to navigate without friction.

The visual style is a blend of **Modern Minimalism** and **Tactile Softness**. It avoids the chaotic visuals of "toy" interfaces in favor of a structured, calm, and spacious environment. The emotional goal is to reduce learning anxiety through high legibility, clear visual hierarchy, and a sense of physical safety conveyed through rounded forms and soft depth.

## Colors
The palette utilizes a "Soft-Vivid" approach. The primary **Soft Purple** acts as the brand’s anchor, providing a modern and creative feel that differentiates from standard "corporate blue." 

- **Primary (#8B5CF6):** Used for main actions, active states, and progress.
- **Success (#10B981):** A gentle mint for positive reinforcement and completed tasks.
- **Warning (#F59E0B):** A soft amber for tips, reminders, and pending items.
- **Error (#EF4444):** A rose-tinted red that signals errors without being unnecessarily alarming.
- **Background (#FAFAFA):** A warm off-white to reduce eye strain compared to pure white.
- **Surface:** Pure white (#FFFFFF) is reserved for cards and elevated components to pop against the warm grey background.

## Typography
This design system utilizes **Quicksand** across all levels. Its rounded terminals mirror the UI’s shape language, making text feel accessible and less intimidating for younger readers.

- **Scale:** Font sizes are intentionally oversized to accommodate developing motor skills and reading levels.
- **Readability:** Body text uses a Medium (500) weight by default to ensure characters are distinct against light backgrounds. 
- **Hierarchy:** Headlines use Bold (700) weights with slightly tighter letter spacing to create a strong visual anchor for lessons and modules.

## Layout & Spacing
The layout follows a **Fluid-Responsive Grid** with an emphasis on "Generous Whitespace." By increasing the gutters and margins, we reduce cognitive load, helping students focus on one task at a time.

- **Desktop:** 12-column grid with 24px gutters and 64px side margins.
- **Tablet:** 8-column grid with 24px gutters and 32px side margins.
- **Mobile:** 4-column grid with 16px gutters and 20px side margins.

Vertical rhythm is strictly maintained using multiples of 8px. Components like cards and input fields should utilize `md` (24px) padding to ensure a spacious, touch-friendly feel.

## Elevation & Depth
Depth is conveyed through **Ambient Shadows** and **Tonal Layering**. The design system avoids harsh black shadows in favor of tinted, diffused shadows that make elements appear to "float" softly above the warm background.

- **Low Elevation:** Used for standard cards. A subtle 4px blur shadow with 5% opacity of the primary color.
- **High Elevation:** Reserved for modals and active popovers. A 16px blur shadow with 10% opacity.
- **Active State:** When a card or button is pressed, it should "sink" (reduce shadow and slightly scale down to 98%) to provide tactile feedback.

## Shapes
The shape language is defined by **High Roundedness**. There are no sharp corners in the interface. This reinforces the "safe" and "friendly" brand attribute.

- **Standard Elements:** Buttons, inputs, and small cards use a 0.5rem (8px) radius.
- **Container Elements:** Learning modules and large feature cards use a 1rem (16px) radius.
- **Interactive Pill:** Secondary buttons and tags use a full pill shape (999px) to distinguish them from primary structural blocks.

## Components
- **Primary Buttons:** High-contrast, Soft Purple background with white text. Use a subtle bottom-border (2px) in a slightly darker shade to give a "pressable" 3D feel.
- **Interactive Cards:** Large hit areas with `spacing.md` padding. On hover, the card should lift slightly and the border color should shift to the primary color.
- **Callout Boxes:** Use light tinted backgrounds (e.g., 10% opacity of Success or Warning colors) with a thick 4px left-accent border to highlight key educational tips.
- **Progress Indicators:** Thick, rounded bars. Use the Success Mint Green for completion. The background track should be a very light grey (#E2E8F0).
- **Chat Bubbles:** Softly rounded corners (radius: 16px), with the tail rounded to match. High contrast between the student’s bubble (Primary Purple) and the mentor’s bubble (White with shadow).
- **Input Fields:** Large height (minimum 48px) with a 2px border. The focus state should use a thick 3px Soft Purple ring with an inner white offset to maintain clarity.