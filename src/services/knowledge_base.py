import os
import datetime
import json
from typing import Optional
import ctypes
from ctypes import wintypes
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from dotenv import load_dotenv
import hashlib
import sys
# 移除 sys.path.insert，因为现在结构已经标准化
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()


def get_short_path(long_path: str) -> str:
    """
    获取 Windows 短路径名（8.3格式），解决中文路径问题
    
    Args:
        long_path: 长路径名（可能包含中文）
    
    Returns:
        短路径名（不含中文）
    """
    if os.name != 'nt':
        return long_path
    
    try:
        buf_size = ctypes.wintypes.MAX_PATH
        buffer = ctypes.create_unicode_buffer(buf_size)
        
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.LPWSTR,
            ctypes.wintypes.DWORD
        ]
        GetShortPathNameW.restype = ctypes.wintypes.DWORD
        
        result = GetShortPathNameW(long_path, buffer, buf_size)
        
        if result != 0:
            return buffer.value
        else:
            return long_path
    except Exception:
        return long_path


def get_index_path_from_knowledge_dir(knowledge_dir: str) -> str:
    """
    根据知识库路径生成索引路径（放在知识库文件夹内部）

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        索引文件路径（在知识库文件夹内部的 .faiss_index/ 目录）
    """
    index_dir = os.path.join(knowledge_dir, ".faiss_index")
    os.makedirs(index_dir, exist_ok=True)

    return index_dir


def get_index_metadata_path(knowledge_dir: str) -> str:
    """
    获取索引元数据文件路径

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        元数据文件路径
    """
    index_dir = get_index_path_from_knowledge_dir(knowledge_dir)
    return os.path.join(index_dir, "index_metadata.json")


def save_index_metadata(knowledge_dir: str, metadata: dict):
    """
    保存索引元数据

    Args:
        knowledge_dir: 知识库目录路径
        metadata: 元数据字典
    """
    metadata_path = get_index_metadata_path(knowledge_dir)

    metadata_data = {
        'knowledge_dir': os.path.abspath(knowledge_dir),
        'build_time': metadata.get('build_time', datetime.datetime.now().isoformat()),
        'knowledge_files': metadata.get('knowledge_files', []),
        'knowledge_files_mtime': metadata.get('knowledge_files_mtime', {})
    }

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_data, f, ensure_ascii=False, indent=2)


def load_index_metadata(knowledge_dir: str) -> dict:
    """
    加载索引元数据

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        元数据字典
    """
    metadata_path = get_index_metadata_path(knowledge_dir)

    if not os.path.exists(metadata_path):
        return {}

    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def should_rebuild_index(knowledge_dir: str) -> bool:
    """
    判断是否需要重新构建索引

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        是否需要重新构建
    """
    metadata = load_index_metadata(knowledge_dir)

    if not metadata:
        print("⚠ 未找到索引元数据，需要构建索引")
        return True

    if not os.path.exists(knowledge_dir):
        print(f"⚠ 知识库目录不存在: {knowledge_dir}")
        return True

    current_files = []
    for root, _, files in os.walk(knowledge_dir):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                current_files.append(file_path)

    if not current_files:
        print("⚠ 知识库目录中没有 Markdown 文件")
        return False

    stored_files = metadata.get('knowledge_files', [])
    stored_mtime = metadata.get('knowledge_files_mtime', {})

    if set(current_files) != set(stored_files):
        print("⚠ 知识库文件发生变化，需要重新构建索引")
        return True

    for file_path in current_files:
        current_mtime = os.path.getmtime(file_path)
        stored_mtime = stored_mtime.get(file_path, 0)

        if current_mtime > stored_mtime:
            print(f"⚠ 文件已更新: {os.path.basename(file_path)}，需要重新构建索引")
            return True

    print("✓ 索引是最新的，无需重新构建")
    return False


def get_current_knowledge_files(knowledge_dir: str) -> list:
    """
    获取当前知识库文件列表

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        文件路径列表
    """
    files = []
    for root, _, filenames in os.walk(knowledge_dir):
        for filename in filenames:
            if filename.endswith(".md") or filename.endswith(".pdf"):
                file_path = os.path.join(root, filename)
                files.append(file_path)
    return files


class CustomEmbeddings(Embeddings):
    """自定义 Embeddings 类，直接调用 API"""
    def __init__(self, api_key, base_url, model_name):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
    
    def embed_documents(self, texts):
        import requests
        embeddings = []
        
        for text in texts:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": self.model_name,
                    "input": text
                }
                
                response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if "data" in result and len(result["data"]) > 0:
                        embedding = result["data"][0]["embedding"]
                        embeddings.append(embedding)
                    else:
                        embeddings.append([0.0] * 1024)
                else:
                    embeddings.append([0.0] * 1024)
                    
            except Exception:
                embeddings.append([0.0] * 1024)
        
        return embeddings
    
    def embed_query(self, text):
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model_name,
            "input": text
        }
        
        response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if "data" in result and len(result["data"]) > 0:
                return result["data"][0]["embedding"]
        
        return [0.0] * 1024


class KnowledgeBaseManager:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, knowledge_dir: Optional[str] = None):
        self.knowledge_dir = knowledge_dir or os.getenv("KNOWLEDGE_DIR", "./knowledge_docs")

        self.vector_db_path = get_index_path_from_knowledge_dir(self.knowledge_dir)

        print(f"知识库路径: {self.knowledge_dir}")
        print(f"索引路径: {self.vector_db_path}")

        embeddings_api_key = api_key or os.getenv("EMBEDDINGS_API_KEY") or os.getenv("LLM_API_KEY")
        embeddings_base_url = base_url or os.getenv("EMBEDDINGS_BASE_URL") or os.getenv("LLM_BASE_URL")
        embeddings_model_name = os.getenv("EMBEDDINGS_MODEL_NAME")

        if embeddings_api_key and embeddings_base_url and embeddings_model_name:
            print(f"使用远程 Embeddings API: {embeddings_model_name}")
            try:
                self.embeddings = CustomEmbeddings(
                    api_key=embeddings_api_key,
                    base_url=embeddings_base_url,
                    model_name=embeddings_model_name
                )
                print("Embeddings 初始化成功！")
            except Exception as e:
                print(f"远程 Embeddings API 初始化失败：{e}")
                print("请检查 API 配置和网络连接")
                self.embeddings = None
        else:
            print("警告：未配置 Embeddings API")
            self.embeddings = None

    def process_pdfs_with_mineru(self, pdf_dir_path: str, use_mineru_cli: bool = False):
        """
        处理 PDF 文件并构建知识库

        Args:
            pdf_dir_path: PDF 文件目录路径
            use_mineru_cli: 是否使用 MinerU CLI 工具（需要提前安装）
        """
        documents = []

        if use_mineru_cli:
            print("使用 MinerU CLI 处理 PDF...")
            self._run_mineru_cli(pdf_dir_path)

        for root, _, files in os.walk(pdf_dir_path):
            for file in files:
                if file.endswith(".md"):
                    loader = UnstructuredMarkdownLoader(os.path.join(root, file))
                    docs = loader.load()
                    documents.extend(docs)

        if not documents:
            print(f"警告：在 {pdf_dir_path} 中未找到 Markdown 文件")
            return None

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        splits = text_splitter.split_documents(documents)

        print(f"正在向量化 {len(splits)} 个知识片段...")

        if self.embeddings:
            try:
                vectorstore = FAISS.from_documents(documents=splits, embedding=self.embeddings)
                vectorstore.save_local(self.vector_db_path)
                print("知识库构建完成！")
                return vectorstore
            except Exception as e:
                print(f"使用当前 embeddings 失败：{e}")
                print("尝试切换到本地 HuggingFace embeddings...")
                try:
                    from langchain_community.embeddings import HuggingFaceEmbeddings
                    self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=self.embeddings)
                    vectorstore.save_local(self.vector_db_path)
                    print("知识库构建完成！（使用本地 embeddings）")
                    return vectorstore
                except Exception as e2:
                    print(f"无法构建向量库：{e2}")
                    return None
        else:
            print("无法构建向量库：embeddings 未初始化")
            return None

    def _run_mineru_cli(self, pdf_dir_path: str):
        """
        调用 MinerU CLI 处理 PDF（需要提前安装 magic-pdf）

        占位符：用户需要确保 MinerU 已安装并配置好
        """
        import subprocess

        for root, _, files in os.walk(pdf_dir_path):
            for file in files:
                if file.endswith(".pdf"):
                    pdf_path = os.path.join(root, file)
                    try:
                        subprocess.run(['magic-pdf', '-p', pdf_path], check=True)
                        print(f"已处理: {pdf_path}")
                    except FileNotFoundError:
                        print(f"错误：未找到 magic-pdf 命令，请先安装 MinerU")
                        print("安装命令：pip install magic-pdf")
                        break
                    except subprocess.CalledProcessError as e:
                        print(f"处理 {pdf_path} 失败：{e}")

    def process_markdown_files(self, md_dir_path: Optional[str] = None):
        """
        直接处理已有的 Markdown 文件（跳过 PDF 解析步骤）
        增强版：添加文档来源和页面位置元数据

        Args:
            md_dir_path: Markdown 文件目录路径（可选，默认使用初始化时指定的路径）
        """
        if not self.embeddings:
            print("错误：未配置 Embeddings API，无法构建知识库")
            print("请在 .env 文件中配置 EMBEDDINGS_BASE_URL")
            return None

        md_dir = md_dir_path or self.knowledge_dir

        if not os.path.exists(md_dir):
            print(f"错误：知识库目录不存在: {md_dir}")
            return None

        documents = []

        for root, _, files in os.walk(md_dir):
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    loader = UnstructuredMarkdownLoader(file_path)
                    docs = loader.load()

                    for doc in docs:
                        doc.metadata['source'] = file
                        doc.metadata['source_path'] = file_path
                        doc.metadata['page'] = 'N/A'
                        doc.metadata['document_type'] = 'markdown'

                    documents.extend(docs)

        if not documents:
            print(f"警告：在 {md_dir} 中未找到 Markdown 文件")
            return None

        print(f"找到 {len(documents)} 个文档片段")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        splits = text_splitter.split_documents(documents)

        print(f"分割为 {len(splits)} 个知识片段")

        for idx, split in enumerate(splits):
            if 'chunk_index' not in split.metadata:
                split.metadata['chunk_index'] = idx

        print(f"正在向量化 {len(splits)} 个知识片段...")

        try:
            vectorstore = FAISS.from_documents(documents=splits, embedding=self.embeddings)
            vectorstore.save_local(self.vector_db_path)
            print("知识库构建完成！")
            print(f"向量索引已保存到: {self.vector_db_path}")
            return vectorstore
        except Exception as e:
            print(f"构建向量库失败：{e}")
            return None

    def search_with_metadata(self, query: str, k: int = 3):
        """
        带元数据的检索，返回详细的文档来源信息

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            包含详细元数据的检索结果列表
        """
        if not self.embeddings:
            print("错误：embeddings 未初始化，无法进行检索")
            return []

        if not os.path.exists(self.vector_db_path):
            print(f"错误：向量索引不存在于 {self.vector_db_path}")
            return []

        try:
            short_path = get_short_path(self.vector_db_path)
            vectorstore = FAISS.load_local(short_path, self.embeddings)
            docs = vectorstore.similarity_search(query, k=k)

            results = []
            for idx, doc in enumerate(docs):
                result = {
                    'id': idx + 1,
                    'content': doc.page_content,
                    'source': doc.metadata.get('source', '未知文档'),
                    'source_path': doc.metadata.get('source_path', ''),
                    'page': doc.metadata.get('page', '未知页码'),
                    'chunk_index': doc.metadata.get('chunk_index', -1),
                    'document_type': doc.metadata.get('document_type', 'unknown'),
                    'relevance_score': max(0.0, 0.95 - (idx * 0.1))
                }
                results.append(result)

            return results
        except Exception as e:
            print(f"检索失败：{e}")
            return []

    def load_existing_index(self):
        """
        加载已存在的向量索引

        Returns:
            FAISS 向量存储对象，如果加载失败则返回 None
        """
        if not self.embeddings:
            print("错误：embeddings 未初始化，无法加载索引")
            return None

        index_dir = self.vector_db_path

        if not os.path.exists(index_dir):
            print(f"错误：向量索引不存在于 {index_dir}")
            print("💡 正在自动构建索引...")
            return self.build_index()

        try:
            print(f"正在加载索引: {os.path.basename(index_dir)}")

            if should_rebuild_index(self.knowledge_dir):
                print("⚠ 检测到索引需要更新，正在自动重新构建...")
                return self.build_index()

            short_path = get_short_path(index_dir)
            vectorstore = FAISS.load_local(short_path, self.embeddings)
            print("✓ 索引加载成功")
            return vectorstore
        except Exception as e:
            print(f"加载向量索引失败：{e}")
            print("💡 正在尝试重新构建索引...")
            return self.build_index()

    def _parse_pdf_with_pymupdf(self, pdf_path: str) -> str:
        """
        使用 PyMuPDF 解析 PDF 文件，返回 Markdown 内容

        Args:
            pdf_path: PDF 文件路径

        Returns:
            Markdown 格式的文本内容
        """
        try:
            import fitz
        except ImportError:
            print("错误：未安装 PyMuPDF，请运行: pip install pymupdf")
            return ""

        try:
            doc = fitz.open(pdf_path)
            
            md_content = ""
            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip():
                    md_content += f"\n\n# 第 {page_num} 页\n\n{text}\n"
            
            doc.close()
            
            if len(md_content) > 100:
                return md_content
            else:
                print(f"警告：PDF 提取内容过少，可能是扫描版 PDF")
                return ""
                
        except Exception as e:
            print(f"PyMuPDF 解析异常: {e}")
            return ""

    def _parse_pdf_with_mineru(self, pdf_path: str) -> str:
        """
        使用 MinerU 解析 PDF 文件，返回 Markdown 内容（首选解析器）

        Args:
            pdf_path: PDF 文件路径

        Returns:
            Markdown 格式的文本内容
        """
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp(prefix="mineru_parse_")

        try:
            from magic_pdf.integrations.rag.api import inference
            
            print(f"使用 MinerU 解析 PDF: {os.path.basename(pdf_path)}")
            
            result = inference(pdf_path, temp_dir, "txt")
            
            if result is None:
                print(f"警告：MinerU 返回 None，可能是模型文件缺失")
                return ""
            
            md_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.md'):
                        md_files.append(os.path.join(root, file))
            
            if not md_files:
                print(f"警告：MinerU 未生成 Markdown 文件")
                return ""
            
            md_content = ""
            for md_file in md_files:
                with open(md_file, 'r', encoding='utf-8') as f:
                    md_content += f.read() + "\n\n"
            
            if len(md_content) > 100:
                print(f"✓ MinerU 解析成功，提取 {len(md_content)} 字符")
                return md_content
            else:
                print(f"警告：MinerU 提取内容过少")
                return ""
                
        except ImportError:
            print("警告：未安装 MinerU，请运行: pip install magic-pdf")
            return ""
        except FileNotFoundError as e:
            if 'yolo_v8_ft.pt' in str(e):
                print(f"警告：MinerU 模型文件缺失，需要下载模型或使用其他解析器")
            else:
                print(f"MinerU 文件未找到异常: {e}")
            return ""
        except Exception as e:
            print(f"MinerU 解析异常: {e}")
            return ""
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def build_index(self):
        """
        构建知识库向量索引（使用 PyMuPDF 解析 PDF）

        Returns:
            FAISS 向量存储对象，如果构建失败则返回 None
        """
        if not self.embeddings:
            print("错误：embeddings 未初始化，无法构建索引")
            return None

        if not os.path.exists(self.knowledge_dir):
            print(f"错误：知识库目录不存在: {self.knowledge_dir}")
            return None

        print("开始构建知识库索引（使用 MinerU 作为首选解析器）...")
        print("-"*60)

        try:
            from langchain_community.document_loaders import UnstructuredMarkdownLoader
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from langchain_community.vectorstores import FAISS

            documents = []
            for root, _, files in os.walk(self.knowledge_dir):
                for file in files:
                    file_path = os.path.join(root, file)

                    if file.endswith(".md"):
                        loader = UnstructuredMarkdownLoader(file_path)
                        docs = loader.load()

                        for doc in docs:
                            doc.metadata['source'] = file
                            doc.metadata['source_path'] = file_path
                            doc.metadata['page'] = 'N/A'
                            doc.metadata['document_type'] = 'markdown'

                        documents.extend(docs)
                    elif file.endswith(".pdf"):
                        md_content = ""
                        parser_used = ""
                        
                        md_content = self._parse_pdf_with_mineru(file_path)
                        if md_content:
                            parser_used = "MinerU"
                        else:
                            print(f"MinerU 解析失败，回退到 PyMuPDF: {file}")
                            md_content = self._parse_pdf_with_pymupdf(file_path)
                            if md_content:
                                parser_used = "PyMuPDF"
                        
                        if md_content:
                            from langchain.schema import Document
                            doc = Document(page_content=md_content)
                            doc.metadata['source'] = file
                            doc.metadata['source_path'] = file_path
                            doc.metadata['page'] = 'N/A'
                            doc.metadata['document_type'] = 'pdf'
                            doc.metadata['parser'] = parser_used
                            documents.append(doc)
                        else:
                            print(f"警告：所有解析器均失败，尝试使用 PyPDFLoader: {file}")
                            from langchain_community.document_loaders import PyPDFLoader
                            loader = PyPDFLoader(file_path)
                            docs = loader.load()

                            for doc in docs:
                                doc.metadata['source'] = file
                                doc.metadata['source_path'] = file_path
                                doc.metadata['page'] = doc.metadata.get('page', 'N/A')
                                doc.metadata['document_type'] = 'pdf'
                                doc.metadata['parser'] = 'PyPDFLoader'

                            documents.extend(docs)

            if not documents:
                print(f"警告：在 {self.knowledge_dir} 中未找到 Markdown 或 PDF 文件")
                return None

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50
            )
            splits = text_splitter.split_documents(documents)

            for idx, split in enumerate(splits):
                if 'chunk_index' not in split.metadata:
                    split.metadata['chunk_index'] = idx

            print(f"已分割为 {len(splits)} 个知识片段")
            print("正在向量化知识片段...")

            vectorstore = FAISS.from_documents(documents=splits, embedding=self.embeddings)
            short_path = get_short_path(self.vector_db_path)
            vectorstore.save_local(short_path)

            knowledge_files = get_current_knowledge_files(self.knowledge_dir)
            metadata = {
                'knowledge_files': knowledge_files,
                'knowledge_files_mtime': {f: os.path.getmtime(f) for f in knowledge_files}
            }
            save_index_metadata(self.knowledge_dir, metadata)

            print("-"*60)
            print("✓ 索引构建成功！")
            print(f"索引已保存到: {self.vector_db_path}")
            print(f"索引文件:")
            if os.path.exists(self.vector_db_path):
                files = os.listdir(self.vector_db_path)
                for file in files:
                    file_path = os.path.join(self.vector_db_path, file)
                    file_size = os.path.getsize(file_path)
                    print(f"  - {file} ({file_size:,} bytes)")
            print("-"*60)
            return vectorstore

        except Exception as e:
            print("-"*60)
            print("✗ 索引构建失败")
            print("-"*60)
            print(f"错误信息: {str(e)}")
            return None


def test_knowledge_base():
    """
    测试知识库管理模块
    """
    print("="*60)
    print("测试 KnowledgeBaseManager 模块")
    print("="*60)
    
    kb_manager = KnowledgeBaseManager()
    
    if not kb_manager.embeddings:
        print("⚠ 警告：未配置 Embeddings API，跳过测试")
        return False
    
    try:
        vectorstore = kb_manager.load_existing_index()
        if vectorstore:
            print(f"✓ 成功加载知识库索引")
            print(f"  索引类型: {type(vectorstore).__name__}")
            print(f"  索引路径: {kb_manager.vector_db_path}")
            print("✓ 知识库管理模块测试通过")
            return True
        else:
            print("⚠ 未找到知识库索引，请先运行 build_knowledge_index.py")
            return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_knowledge_base()
