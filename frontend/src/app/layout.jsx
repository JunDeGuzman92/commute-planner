import "./globals.css";

export const metadata = {
  title: "Durham Commute Planner",
  description: "Multi-modal trip planning with DRT GTFS and real-time updates",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}