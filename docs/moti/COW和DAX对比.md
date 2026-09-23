# 问题

* DAX相比blk的主要优势：
  * 文件内容直接映射，而不是从cache miss到块路径，速度快
  * 多个沙箱共享相同文件内容，避免重复guest page cache
    * 初始化沙箱时，若有相同镜像层则可直接共享
    * 自己的私有修改也变为DAX，之后fork出来的子沙箱也可共享
* 但是blk文件系统可以实现类似的优势
  * guest page cache也是guest内存，可以存入guest内存映像
  * fork出子沙箱也只有一份内存，共享page cache

# 区别

* 读热数据（在page cache中）
  * 都按需加载进内存，子沙箱间共享
  * host page cache只有一份，也都不进入块路径

* 写文件
  * 两者都写到blk中。新page cache $\to$ OverlayBD新层中的块
    * fs层面：开启Direct IO，都会写入磁盘文件
    * 子沙箱读：都按需加载，都只有一份host page cache
    * 子沙箱写：、
      * **AgentENV：先copy一份，然后修改cache，再反映到fs**
      * DAX：直接分配新的page cache，无copy

* 读冷数据：不在page cache中
  * AgentENV：**不同子沙箱即使读同一个文件，都自己建立新的page cache**
    * 时延：都经历冷的块读取路径
    * 内存：作为私有guest page cache，分开保存至内存snapshot中
      * miss一次就有一份，可能有很多snapshot保存相同的文件内容

  * DAX：仍然只在host有一份page cache
    * 基础镜像中：始终只有一份
    * 某沙箱的私有修改：对应每个修改有一份

  * 从同一个充分预热的沙箱派生且读多，则DAX优势不大

* 冗余共享
  * AgentENV：cache需要另外加载一份以共享
    * A派生B、C
    * 相同page cache在A中存在，但仍需要复制一份给B C共享
    * **对于大量分支和长程任务：每fork一次就需要复制一次page cache**
    * 本质：无法直接共享A中的文件内存

  * DAX：**文件只有一个身份**
    * Checkpoint后，A1丢弃page cache，文件内容固化为DAX
    * A B C访问相同文件只会对应同一个host page cache

