import type { Metadata } from 'next';
import LandingClient from './LandingClient';
import './landing.css';

export const metadata: Metadata = {
  title: 'Refloat — AI growth platform for Indian MSMEs',
  description:
    'Refloat is an AI-powered business growth platform for Indian MSMEs. Health monitoring, marketing automation, export discovery, and government schemes — in one mobile app and web dashboard.',
  openGraph: {
    title: 'Refloat — Your business has a pulse.',
    description: 'The first AI growth assistant built for Indian MSMEs. Mobile + web, perfectly synced.',
    type: 'website',
  },
};

const orgJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Refloat',
  url: 'https://refloat.in',
  description: 'AI growth platform for Indian MSMEs',
  areaServed: 'IN',
};

export default function LandingPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
      />
      <LandingClient />
    </>
  );
}
