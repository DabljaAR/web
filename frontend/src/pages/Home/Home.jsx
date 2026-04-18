import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import InstallAppButton from '../../components/common/InstallAppButton';
import HeroSection from '../../components/home/HeroSection';
import ProblemSection from '../../components/home/ProblemSection';
import FeaturesSection from '../../components/home/FeaturesSection';
import HowItWorksSection from '../../components/home/HowItWorksSection';
import DemoSection from '../../components/home/DemoSection';
import TeamSection from '../../components/home/TeamSection';
import TryItNowSection from '../../components/home/TryItNowSection';
import Footer from '../../components/layout/Footer';
import '../../styles/home.css';

const Home = () => {
  const location = useLocation();

  useEffect(() => {
    const hash = location.hash;
    if (!hash || hash.length < 2) return;

    const sectionId = hash.slice(1);
    const element = document.getElementById(sectionId);
    if (!element) return;

    // Let the page render/layout settle before scrolling.
    setTimeout(() => {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  }, [location.hash]);

  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <div className="pwa-install-fab" aria-label="Install app">
        <InstallAppButton className="pwa-install-fab-btn" />
      </div>
      <HeroSection />
      <ProblemSection />
      <HowItWorksSection />
      <TryItNowSection />
      <TeamSection />
      <Footer />
    </div>
  );
};

export default Home;
