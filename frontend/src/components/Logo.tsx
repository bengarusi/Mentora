import logoSrc from "../assets/logo.png";

interface LogoProps {
  size?: number;
  className?: string;
}

/** The Mentora mark, exactly as provided. */
export function Logo({ size = 28, className }: LogoProps) {
  return (
    <img
      src={logoSrc}
      alt=""
      width={size}
      height={size}
      className={className}
      style={{ objectFit: "contain" }}
    />
  );
}
