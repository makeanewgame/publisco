import { Outlet } from 'react-router-dom';
import { Footer } from '../components/Footer';
import { FloatingThemeToggle } from '../components/FloatingThemeToggle';
import { Navbar } from '../components/Navbar';

export function RootLayout() {
  return (
    <div className='min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(20,183,140,0.14),_transparent_28%),linear-gradient(135deg,_#fcf5eb_0%,_#f8ebdc_100%)] text-[#241c15] py-8'>
      <Navbar />
      <Outlet />
      <Footer />
    </div>
  );
}
