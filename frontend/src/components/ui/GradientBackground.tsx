/**
 * GradientBackground — three animated gradient orbs matching the glassmorphism mock.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/home.html
 * CSS classes: .gradient-bg, .gradient-orb, .orb-1/2/3 (defined in globals.css)
 */

export function GradientBackground() {
  return (
    <div className="gradient-bg" aria-hidden="true">
      <div className="gradient-orb orb-1" />
      <div className="gradient-orb orb-2" />
      <div className="gradient-orb orb-3" />
    </div>
  );
}
