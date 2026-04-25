import time
import random
import logging

class HumanHelper:
    """
    Helper class to simulate human-like behavior in browser automation.
    """
    
    @staticmethod
    def esperar_humano(min_seg=1.0, max_seg=3.0):
        """Espera aleatória para simular comportamento humano"""
        delay = random.uniform(min_seg, max_seg)
        logging.debug(f"Aguardando {delay:.2f}s (comportamento humano)")
        time.sleep(delay)

    @staticmethod
    def digitar_como_humano(locator, texto):
        """
        Digita texto com delays aleatórios entre cada caractere
        para simular digitação humana.
        """
        logging.info(f"Digitando texto com comportamento humano...")
        
        # Clicar no campo primeiro
        locator.click()
        HumanHelper.esperar_humano(0.3, 0.7)
        
        # Limpar campo
        locator.fill("")
        HumanHelper.esperar_humano(0.2, 0.5)
        
        # Digitar caractere por caractere
        for i, char in enumerate(texto):
            locator.type(char, delay=random.uniform(80, 200))  # delay entre 80-200ms
            
            # Ocasionalmente fazer uma pausa mais longa (como se estivesse pensando)
            if random.random() < 0.1:  # 10% de chance
                time.sleep(random.uniform(0.3, 0.8))

    @staticmethod
    def mover_mouse_e_clicar(page, locator):
        """
        Move o mouse até o elemento e clica, simulando comportamento humano.
        """
        try:
            # Obter posição do elemento
            box = locator.bounding_box()
            if box:
                # Mover para perto do elemento
                x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                page.mouse.move(x, y)
                HumanHelper.esperar_humano(0.1, 0.3)
                
                # Clicar
                locator.click()
            else:
                # Fallback: clicar direto
                locator.click()
        except Exception as e:
            logging.warning(f"Erro ao mover mouse: {e}")
            locator.click()

    @staticmethod
    def scroll_suave(page, pixels=None):
        """Faz scroll suave na página para simular leitura"""
        if pixels is None:
            pixels = random.randint(100, 300)
        
        page.mouse.wheel(0, pixels)
        HumanHelper.esperar_humano(0.3, 0.6)
