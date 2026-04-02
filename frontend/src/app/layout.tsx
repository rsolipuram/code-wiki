import type { Metadata } from "next";
import { Outfit, Fira_Code } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const firaCode = Fira_Code({
  variable: "--font-fira-code",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Code Wiki — AI-Powered Code Documentation",
  description:
    "Automatically generate and maintain comprehensive wiki documentation for any code repository.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark">
      <body className={`${outfit.variable} ${firaCode.variable}`}>
        <ThemeProvider>
          {children}
          <div
            style={{
              position: "fixed",
              top: 16,
              right: 16,
              zIndex: 9999,
            }}
          >
            <ThemeToggle />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
