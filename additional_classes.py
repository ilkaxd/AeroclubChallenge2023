class City:
    def __init__(self, idx, name, name_english, country, code, timeZone):
        self.idx = idx
        self.name = name
        self.name_english = name_english
        self.country = country
        self.code = code
        self.timeZone = timeZone
        self.aeroports = []

    def __str__(self):
        aeroports = ', '.join(x.name for x in self.aeroports)
        return f'{self.name} - {self.name_english} ({self.idx}|{self.code}|{self.country}|{aeroports}) {self.timeZone}'

    def __repr__(self):
        return self.__str__()


class Aeroport:
    def __init__(self, idx, city, name, name_english, code):
        self.idx = idx
        self.city = city
        self.name = name
        self.name_english = name_english
        self.code = code

    def __str__(self):
        return f'{self.name} - {self.name_english} ({self.idx}|{self.code}|{self.city.name})'

    def __repr__(self):
        return self.__str__()
