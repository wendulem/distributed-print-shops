from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    
    def distance_to(self, other: 'Location') -> float:
        """Calculate distance in miles using Haversine formula"""
        R = 3959.87433  # Earth's radius in miles

        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

    def to_dict(self) -> dict:
        """Convert location to dictionary format"""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude
        }