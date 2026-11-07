import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/layout/providers";

export const metadata: Metadata = {
  title: "Wingman — Cluster Management",
  description: "OpenShift HostedControlPlane lifecycle management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
