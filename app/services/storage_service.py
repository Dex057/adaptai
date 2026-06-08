"""
Service para gerenciamento de arquivos de materiais no storage
"""
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any


class StorageService:
    """Service para gerenciar arquivos de materiais"""
    
    def __init__(self):
        """Inicializa o service e cria diretório de storage"""
        # Diretório base: backend/storage/materiais/
        self.storage_dir = Path(__file__).parent.parent.parent / "storage" / "materiais"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, material_id: int, tipo: str) -> Path:
        """
        Retorna o caminho completo do arquivo
        
        Args:
            material_id: ID do material
            tipo: 'html' ou 'json'
        
        Returns:
            Path completo do arquivo
        """
        extensao = "html" if tipo == "html" else "json"
        filename = f"{material_id}.{extensao}"
        return self.storage_dir / filename
    
    def salvar_html(self, material_id: int, html_content: str) -> str:
        """
        Salva conteúdo HTML em arquivo
        
        Args:
            material_id: ID do material
            html_content: Conteúdo HTML como string
        
        Returns:
            Nome do arquivo salvo (ex: "123.html")
        """
        file_path = self._get_file_path(material_id, "html")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"💾 HTML salvo: {file_path}")
        return f"{material_id}.html"
    
    def salvar_json(self, material_id: int, json_data: Dict[Any, Any]) -> str:
        """
        Salva dados JSON em arquivo
        
        Args:
            material_id: ID do material
            json_data: Dados como dicionário Python
        
        Returns:
            Nome do arquivo salvo (ex: "123.json")
        """
        file_path = self._get_file_path(material_id, "json")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 JSON salvo: {file_path}")
        return f"{material_id}.json"
    
    def ler_html(self, material_id: int) -> Optional[str]:
        """
        Lê conteúdo HTML do arquivo
        
        Args:
            material_id: ID do material
        
        Returns:
            Conteúdo HTML ou None se não encontrado
        """
        file_path = self._get_file_path(material_id, "html")
        
        if not file_path.exists():
            print(f"⚠️ Arquivo HTML não encontrado: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def ler_json(self, material_id: int) -> Optional[Dict[Any, Any]]:
        """
        Lê dados JSON do arquivo
        
        Args:
            material_id: ID do material
        
        Returns:
            Dados como dicionário ou None se não encontrado
        """
        file_path = self._get_file_path(material_id, "json")
        
        if not file_path.exists():
            print(f"⚠️ Arquivo JSON não encontrado: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def deletar(self, material_id: int) -> bool:
        """
        Deleta todos os arquivos de um material (HTML e JSON se existirem)
        
        Args:
            material_id: ID do material
        
        Returns:
            True se deletou pelo menos um arquivo, False caso contrário
        """
        deletou_algum = False
        
        # Tentar deletar HTML
        html_path = self._get_file_path(material_id, "html")
        if html_path.exists():
            html_path.unlink()
            print(f"🗑️ HTML deletado: {html_path}")
            deletou_algum = True
        
        # Tentar deletar JSON
        json_path = self._get_file_path(material_id, "json")
        if json_path.exists():
            json_path.unlink()
            print(f"🗑️ JSON deletado: {json_path}")
            deletou_algum = True
        
        return deletou_algum
    
    def existe(self, material_id: int, tipo: str = None) -> bool:
        """
        Verifica se arquivo do material existe
        
        Args:
            material_id: ID do material
            tipo: 'html', 'json' ou None (verifica ambos)
        
        Returns:
            True se existe, False caso contrário
        """
        if tipo:
            file_path = self._get_file_path(material_id, tipo)
            return file_path.exists()
        else:
            # Verifica se HTML ou JSON existe
            html_path = self._get_file_path(material_id, "html")
            json_path = self._get_file_path(material_id, "json")
            return html_path.exists() or json_path.exists()

    def _get_versioned_path(self, material_id: int, versao: int, tipo: str) -> Path:
        """Caminho do arquivo de uma versao arquivada (ex: 123_v2.html)."""
        extensao = "html" if tipo == "html" else "json"
        return self.storage_dir / f"{material_id}_v{versao}.{extensao}"

    def arquivar_versao(self, material_id: int, versao: int, tipo: str) -> Optional[str]:
        """Copia o arquivo atual para um nome versionado. Retorna o nome do arquivo ou None."""
        atual = self._get_file_path(material_id, tipo)
        if not atual.exists():
            return None
        destino = self._get_versioned_path(material_id, versao, tipo)
        shutil.copy2(atual, destino)
        print(f"🗂️ Versão arquivada: {destino}")
        return destino.name

    def ler_versao(self, material_id: int, versao: int, tipo: str):
        """Le o conteudo de uma versao arquivada (HTML como str, JSON como dict). None se nao existir."""
        path = self._get_versioned_path(material_id, versao, tipo)
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            if tipo == "html":
                return f.read()
            return json.load(f)


# Instância global do service
storage_service = StorageService()
