import type { Metadata } from "next";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

// Dupla tipográfica do protótipo: Space Grotesk carrega o texto (tem o
// desenho meio técnico que combina com a identidade) e IBM Plex Mono é
// reservada a rótulo e número — mono aqui não significa "código", significa
// "dado medido". Os pesos são só os realmente usados no design system
// (400/500/600/700 no sans, 400/500/600 no mono); pedir a família inteira
// baixaria arquivo que nenhuma tela renderiza.
const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "FerrarIA — tutor de concursos",
  description: "Tutor socrático para concursos públicos brasileiros",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      // `dark` fixo, sem `prefers-color-scheme`: o design system é escuro
      // por identidade, não por preferência do SO (ver globals.css).
      className={`${spaceGrotesk.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      <body className="h-full">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
