/// <reference types="@types/google.maps" />
import { useEffect, useRef } from 'react';
import { Loader } from '@googlemaps/js-api-loader';

interface MapProps {
  lat: number;
  lng: number;
  zoom?: number;
}

export const GoogleMap = ({ lat, lng, zoom = 15 }: MapProps) => {
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loader = new Loader({
      apiKey: import.meta.env.VITE_MAPS_API_KEY || '',
      version: 'weekly',
    });

    loader.load().then(async () => {
      if (!mapRef.current) return;
      
      const { Map } = await google.maps.importLibrary("maps") as google.maps.MapsLibrary;
      const { AdvancedMarkerElement } = await google.maps.importLibrary("marker") as google.maps.MarkerLibrary;

      const map = new Map(mapRef.current, {
        center: { lat, lng },
        zoom,
        mapId: 'DEMO_MAP_ID', // Better for advanced markers
        backgroundColor: 'var(--bg-glass)', // Match design
      });

      new AdvancedMarkerElement({
        map,
        position: { lat, lng },
        title: "Incident Location",
      });
    });
  }, [lat, lng, zoom]);

  return (
    <div 
      ref={mapRef} 
      className="map-container-sdk"
      style={{ 
        width: '100%', 
        height: '300px', 
        borderRadius: '16px', 
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.1)'
      }} 
    />
  );
};
