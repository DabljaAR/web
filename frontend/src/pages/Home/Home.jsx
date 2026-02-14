import React from 'react';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
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
  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <HeroSection />
      <ProblemSection />
      <FeaturesSection />
      <HowItWorksSection />
      <TryItNowSection />
      {/* <DemoSection /> */}
      <TeamSection />
      <Footer />
    </div>
  );
};

export default Home;
